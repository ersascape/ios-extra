"""Exercise the actual patch's opt-in and MMIO mapping boundaries on the host.

Only the ARM memory-barrier instruction is replaced for host execution.
The real source is also cross-compiled separately against XNU headers.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GPUProbeTests(unittest.TestCase):
    def test_mmio_boundaries(self):
        with tempfile.TemporaryDirectory(prefix='ios-extra-gpu-test-') as directory:
            work = Path(directory)
            for patch in sorted((ROOT / 'xnu/patches').glob('*.patch')):
                if b'+++ b/bsd/dev/sweet_gpu.c\n' in patch.read_bytes():
                    subprocess.run(['git', 'apply', '--include=bsd/dev/sweet_gpu.c',
                                    str(patch)], cwd=work, check=True)
            source = (work / 'bsd/dev/sweet_gpu.c').read_text()
            barrier = '__asm__ volatile("dmb oshld" ::: "memory");'
            self.assertEqual(source.count(barrier), 2)
            for name in ('dmb oshld', 'dmb oshst', 'dsb osh'):
                text = '__asm__ volatile("%s" ::: "memory");' % name
                self.assertEqual(source.count(text), 2)  # 32- and 64-bit accessors
                source = source.replace(text, '__asm__ volatile("" ::: "memory");')
            (work / 'sweet_gpu.c').write_text(source)
            headers = {
                'sys/param.h': '#include <stdint.h>\ntypedef uintptr_t vm_offset_t;\n'
                               'typedef uintptr_t vm_size_t;\n',
                'sys/systm.h': '',
                'kern/clock.h': 'void delay(int);\n',
                'arm/caches_internal.h': '#define TRUE 1\ntypedef unsigned long long addr64_t;\n'
                                         'void clean_dcache64(addr64_t, unsigned, int);\n',
                'vm/pmap.h': 'typedef unsigned long long addr64_t;\ntypedef unsigned int ppnum_t;\n'
                             'typedef void *pmap_t;\nextern pmap_t kernel_pmap;\n'
                             '#define ptoa_64(x) ((unsigned long long)(x) << 14)\n',
                'vm/vm_kern.h': 'typedef int kern_return_t;\ntypedef void *vm_map_t;\n'
                                'extern vm_map_t kernel_map;\n#define KERN_SUCCESS 0\n'
                                '#define PAGE_MASK 0x3fffUL\n#define KMA_DATA 1\n#define KMA_ZERO 2\n'
                                '#define KMA_PERMANENT 4\n#define VM_KERN_MEMORY_IOKIT 0\n'
                                'kern_return_t kmem_alloc_contig(vm_map_t, vm_offset_t *, vm_size_t, '
                                'vm_offset_t, unsigned, unsigned, unsigned, int);\n',
                'pexpert/pexpert.h': 'int PE_parse_boot_argn(const char *, void *, int);\n',
            }
            for name, text in headers.items():
                path = work / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            # Deterministic stand-in for the staged (not committed) firmware header.
            fw = bytes((i * 7 + 3) & 255 for i in range(0x8000))
            (work / 'sweet_gpu_fw.h').write_text(
                'static const unsigned char sweet_gpu_gmu_fw[] = {%s};\n' %
                ','.join(str(b) for b in fw))
            (work / 'test.c').write_text(HARNESS)
            build = subprocess.run([shutil.which('cc') or 'cc', '-std=c11', '-Wall',
                                    '-Wextra', '-Werror', *os.environ.get('IOS_EXTRA_CFLAGS', '').split(), '-I', str(work),
                                    str(work / 'test.c'), '-o', str(work / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run([str(work / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS: 14 clock/cache cases, 30 ARC cases + 512 mutations, 47 CX experiment cases', result.stdout)


HARNESS = r'''
#include <assert.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int probe_printf(const char *, ...);
#define printf probe_printf
#define ARM64_BOARD_CONFIG_SWEET 1
#include "sweet_gpu.c"
#undef printf

static uint32_t gcc[0x90000 / 4], cc[0x9000 / 4];
static int present, mode, map_calls, fail_gcc, fail_cc;
static uint32_t locator[2], database[1024];
static uint32_t gmu_mem[GPU_GMU_SIZE / 4];
static int gmu_maps, fail_gmu_map;
/* Fake DMA page, SMMU ATOS model and cache-clean counters (sweetgpu=8). */
static unsigned char dma_block[0x4000] __attribute__((aligned(16384)));
static unsigned long long fake_pa_base;
static int fail_alloc, alloc_calls, clean_calls, ats_stuck, tlb_stuck;
static uint64_t last_ats;
pmap_t kernel_pmap; vm_map_t kernel_map;
static uint32_t smmu_mem[GPU_SMMU_SIZE / 4];
static int smmu_maps, fail_smmu_map;
/* Simulated GPUCC CX GDSC and RPMh ARC client for the sweetgpu=3 experiment. */
static int gdsc_hw_ok, delay_calls, vote_fail_on, rcg_stuck;
static unsigned clk_stuck;
static unsigned vote_count, vote_seq[8];
static char vote_name[8][8];
static int fail_locator, fail_db;
static char output[65536];

static uint64_t smmu_rd64(unsigned off) { return smmu_mem[off / 4] | (uint64_t)smmu_mem[off / 4 + 1] << 32; }
static uint64_t dma_rd64(unsigned long long pa) {
    return *(uint64_t *)(dma_block + (pa - fake_pa_base));
}
/* Minimal AArch64 4 KiB-granule walker standing in for the SMMU's ATOS unit. */
static void smmu_sim(void)
{
    const unsigned cb = GPU_SMMU_CB0 + 3 * 0x1000;
    uint64_t cur = smmu_rd64(cb + GPU_SMMU_CB_ATS1PR);
    if (cur == last_ats) return;
    last_ats = cur;
    smmu_mem[(cb + GPU_SMMU_CB_ATSR) / 4] = ats_stuck ? 1 : 0;
    uint64_t par = 1; /* fault */
    uint32_t tcr = smmu_mem[(cb + GPU_SMMU_CB_TCR) / 4];
    if ((smmu_mem[cb / 4] & 1u) && (tcr & 0x3f) == 32 && !(tcr & (3u << 14))) {
        uint64_t va = cur & 0xffffffffu, t = smmu_rd64(cb + GPU_SMMU_CB_TTBR0) & 0xfffffffff000ull;
        uint64_t e1 = dma_rd64(t + 8 * ((va >> 30) & 3));
        if ((e1 & 3) == 3) {
            uint64_t e2 = dma_rd64((e1 & 0xfffffffff000ull) + 8 * ((va >> 21) & 511));
            if ((e2 & 3) == 3) {
                uint64_t e3 = dma_rd64((e2 & 0xfffffffff000ull) + 8 * ((va >> 12) & 511));
                if ((e3 & 3) == 3 && (e3 & (1u << 10))) par = e3 & 0x0000fffffffff000ull;
            }
        }
    }
    smmu_mem[(cb + GPU_SMMU_CB_PAR) / 4] = (uint32_t)par;
    smmu_mem[(cb + GPU_SMMU_CB_PAR) / 4 + 1] = (uint32_t)(par >> 32);
}

void clean_dcache64(addr64_t addr, unsigned count, int phys) { (void)addr; (void)count; (void)phys; clean_calls++; }
ppnum_t pmap_find_phys(pmap_t p, addr64_t va)
{
    (void)p; return (ppnum_t)((fake_pa_base + (va - (addr64_t)(uintptr_t)dma_block)) >> 14);
}
kern_return_t kmem_alloc_contig(vm_map_t m, vm_offset_t *a, vm_size_t size, vm_offset_t mask,
    unsigned x1, unsigned x2, unsigned flags, int tag)
{
    (void)m; (void)x1; (void)x2; (void)tag; (void)mask;
    alloc_calls++;
    assert(size <= sizeof(dma_block) && (flags & 2));
    if (fail_alloc) return 1;
    memset(dma_block, 0, sizeof(dma_block));
    *a = (vm_offset_t)dma_block;
    return KERN_SUCCESS;
}

void delay(int us)
{
    smmu_sim();
    (void)us; delay_calls++;
    uint32_t *mn = &gcc[GPU_GCC_MEMNOC_GFX / 4];
    if (!(clk_stuck & 8u)) { if (*mn & 1u) *mn &= ~GPU_BRANCH_OFF; else *mn |= GPU_BRANCH_OFF; }
    static const unsigned cb[3] = { GPU_CC_AHB, GPU_CC_CX_GMU, GPU_CC_CXO };
    for (unsigned i = 0; i < 3; i++) {
        uint32_t *c = &cc[cb[i] / 4];
        if (clk_stuck & (1u << i)) continue;
        if (*c & 1u) *c &= ~GPU_BRANCH_OFF; else *c |= GPU_BRANCH_OFF;
    }
    if (!rcg_stuck) cc[GPU_GMU_RCG_CMD / 4] &= ~GPU_RCG_UPDATE;
    uint32_t *g = &cc[GPU_CX_GDSCR / 4];
    if (!gdsc_hw_ok) return;
    if (*g & 1u) *g &= ~GPU_DOMAIN_ON; else *g |= GPU_DOMAIN_ON;
}

int sweet_rpmh_arc_set(const char *res, unsigned corner, unsigned *level)
{
    assert(vote_count < 8);
    strncpy(vote_name[vote_count], res, 7);
    vote_seq[vote_count++] = corner;
    if (level) *level = corner ? 2 : 0;
    if ((int)vote_count == vote_fail_on) return 5;
    return 0;
}

static int probe_printf(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    size_t used = strlen(output);
    int count = vsnprintf(output + used, sizeof(output) - used, fmt, ap);
    va_end(ap);
    assert(count >= 0 && (size_t)count < sizeof(output) - used);
    return count;
}

int PE_parse_boot_argn(const char *name, void *value, int length)
{
    assert(strcmp(name, "sweetgpu") == 0 && length == sizeof(mode));
    if (present) memcpy(value, &mode, sizeof(mode));
    return present;
}

vm_offset_t ml_io_map(vm_offset_t physical, vm_size_t size)
{
    map_calls++;
    if (physical == GPU_GCC_PA && size == GPU_GCC_SIZE)
        return fail_gcc ? 0 : (vm_offset_t)gcc;
    if (physical == GPU_CC_PA && size == GPU_CC_SIZE)
        return fail_cc ? 0 : (vm_offset_t)cc;
    if (physical == GPU_SMMU_PA && size == GPU_SMMU_SIZE) {
        smmu_maps++;
        return fail_smmu_map ? 0 : (vm_offset_t)smmu_mem;
    }
    if (physical == GPU_GMU_PA && size == GPU_GMU_SIZE) {
        gmu_maps++;
        return fail_gmu_map ? 0 : (vm_offset_t)gmu_mem;
    }
    if (physical == GPU_DB_LOCATOR_PA && size == 8)
        return fail_locator ? 0 : (vm_offset_t)locator;
    if (physical == 0x85fe0000u && size == sizeof(database))
        return fail_db ? 0 : (vm_offset_t)database;
    assert(!"probe tried to map a GPU/GMU/SMMU or unknown region");
    return 0;
}

static void reset(void)
{
    memset(gcc, 0, sizeof(gcc));
    memset(cc, 0, sizeof(cc));
    output[0] = 0;
    present = mode = 1;
    map_calls = fail_gcc = fail_cc = 0;
    fail_locator = fail_db = 0;
    memset(database, 0, sizeof(database));
    locator[0] = 0x85fe0000u; locator[1] = sizeof(database);
    memset(&gpu_boot_inventory, 0, sizeof(gpu_boot_inventory));
    gpu_inventory_ready = gpu_replay_count = 0;
    gdsc_hw_ok = 1; delay_calls = vote_fail_on = 0; vote_count = 0;
    rcg_stuck = 0; clk_stuck = 0;
    memset(vote_name, 0, sizeof(vote_name));
    gcc[GPU_CFG_AHB_CBCR / 4] = GPU_BRANCH_ENABLE;
}

static void db16(unsigned offset, uint16_t value)
{
    unsigned char *bytes = (unsigned char *)database;
    assert(offset + 2 <= sizeof(database));
    bytes[offset] = value & 255; bytes[offset + 1] = value >> 8;
}

static void db32(unsigned offset, uint32_t value)
{
    assert(!(offset & 3) && offset + 4 <= sizeof(database));
    database[offset / 4] = value;
}

static void arc_reset(void)
{
    reset(); mode = 2;
    gcc[GPU_GCC_GPLL0_MODE / 4] = GPU_PLL_LOCK_DET | 7u;
    gcc[GPU_GCC_GPLL0_VOTE / 4] = 1;
    gcc[GPU_GCC_GPU_GPLL_VOTE / 4] = 1u << 15;
    /* Phone-measured: ABL leaves ahb/cxo enabled (running once CX is on). */
    cc[GPU_CC_AHB / 4] = cc[GPU_CC_CXO / 4] = 0x00000001u;
    cc[GPU_CC_CX_GMU / 4] = 0x80004220u;
    gcc[GPU_GCC_MEMNOC_GFX / 4] = 0x80000220u; gcc[GPU_GCC_DDRSS_GPU_AXI / 4] = 0;
    gmu_maps = fail_gmu_map = smmu_maps = fail_smmu_map = 0;
    for (unsigned i = 0; i < GPU_SMMU_SIZE / 4; i++) smmu_mem[i] = 0x5e000000u | i;
    smmu_mem[0x20 / 4] = 5;    /* IDR0: NUMSMRG = 5 */
    smmu_mem[0x24 / 4] = 3;    /* IDR1: NUMCB = 3 */
    fake_pa_base = 0x90000000ull; fail_alloc = alloc_calls = clean_calls = 0;
    ats_stuck = tlb_stuck = 0;
    last_ats = smmu_rd64(GPU_SMMU_CB0 + 3 * 0x1000 + GPU_SMMU_CB_ATS1PR); /* not a pending request */
    memset(dma_block, 0, sizeof(dma_block));
    for (unsigned i = 0; i < GPU_GMU_SIZE / 4; i++) gmu_mem[i] = 0xa5000000u | i;
    cc[GPU_GMU_RCG_CMD / 4] = 0x80000000u; cc[GPU_GMU_RCG_CFG / 4] = 0x100u;
    db32(0, 1); db32(4, GPU_DB_MAGIC);
    db16(8, 3); db16(10, 0); db16(12, 128); db16(14, 3); db16(16, 0x100);
    for (unsigned r = 0; r < 3; r++) {
        unsigned e = GPU_DB_HEADER + GPU_DB_ENTRY * r;
        unsigned data = GPU_DB_HEADER + 128 + 32 * r;
        unsigned char *bytes = (unsigned char *)database;
        memcpy(bytes + e, gpu_arc_names[r], strlen(gpu_arc_names[r]));
        db32(e + 8, 1u << r); db32(e + 12, 0x12345678);
        db32(e + 16, 0x30000 + 4 * r);
        db16(e + 20, 8); db16(e + 22, 32 * r);
        db16(data, 0); db16(data + 2, 48); db16(data + 4, 128); db16(data + 6, 0);
    }
}

static struct gpu_arc_inventory *arc_run(void)
{
    uint32_t before[1024], loc_before[2];
    memcpy(before, database, sizeof(before)); memcpy(loc_before, locator, sizeof(locator));
    sweet_gpu_probe();
    assert(!memcmp(before, database, sizeof(before)));
    assert(!memcmp(loc_before, locator, sizeof(locator)));
    return &gpu_boot_inventory.arc;
}

int main(void)
{
    reset(); present = 0; sweet_gpu_probe();
    assert(map_calls == 0 && output[0] == 0);
    reset(); mode = 0; sweet_gpu_probe(); assert(map_calls == 0);
    reset(); mode = 9; sweet_gpu_probe(); assert(map_calls == 0);
    reset(); mode = -1; sweet_gpu_probe(); assert(map_calls == 0);
    reset(); fail_gcc = 1; sweet_gpu_probe();
    assert(map_calls == 1 && strstr(output, "GCC mapping failed"));
    reset(); gcc[GPU_CFG_AHB_CBCR / 4] = 0; sweet_gpu_probe();
    assert(map_calls == 1 && strstr(output, "GPUCC skipped"));
    reset(); gcc[GPU_CFG_AHB_CBCR / 4] = GPU_BRANCH_ENABLE | GPU_BRANCH_OFF;
    sweet_gpu_probe(); assert(map_calls == 1 && strstr(output, "GPUCC skipped"));
    reset(); gcc[GPU_CFG_AHB_CBCR / 4] = ~0u; sweet_gpu_probe();
    assert(map_calls == 1 && strstr(output, "invalid") && strstr(output, "GPUCC skipped"));
    reset(); fail_cc = 1; sweet_gpu_probe();
    assert(map_calls == 2 && strstr(output, "GPUCC mapping failed"));
    reset(); sweet_gpu_probe();
    assert(map_calls == 2 && strstr(output, "GPU/GMU/SMMU skipped"));
    assert(gcc[GPU_CFG_AHB_CBCR / 4] == GPU_BRANCH_ENABLE);
    for (unsigned i = 0; i < sizeof(cc) / sizeof(cc[0]); i++) assert(cc[i] == 0);
    reset(); cc[GPU_CX_GDSCR / 4] = cc[GPU_GX_GDSCR / 4] = ~0u;
    sweet_gpu_probe(); assert(map_calls == 2 && strstr(output, "PWR_ON=unknown"));
    assert(cc[GPU_CX_GDSCR / 4] == ~0u && cc[GPU_GX_GDSCR / 4] == ~0u);
    reset(); present = 0; sweet_gpu_probe(); sweet_gpu_replay();
    assert(map_calls == 0 && output[0] == 0);
    reset(); cc[GPU_CX_GDSCR / 4] = 0x80000004u; sweet_gpu_probe();
    assert(map_calls == 2);
    memset(gcc, 0xff, sizeof(gcc)); memset(cc, 0xff, sizeof(cc));
    fail_gcc = fail_cc = 1;
    output[0] = 0; sweet_gpu_replay();
    assert(map_calls == 2 && strstr(output, "report 1 (cached=1)"));
    assert(strstr(output, "0x80000004") && strstr(output, "0x00000001"));
    assert(!strstr(output, "0xffffffff") && strstr(output, "END boot inventory report 1"));
    output[0] = 0; sweet_gpu_replay();
    assert(map_calls == 2 && strstr(output, "report 2 (cached=1)"));
    reset(); fail_gcc = 1; sweet_gpu_probe(); output[0] = 0;
    fail_gcc = 0; sweet_gpu_replay();
    assert(map_calls == 1 && strstr(output, "GCC mapping failed"));
    assert(strstr(output, "END boot inventory report 1"));
    /* Separate ARC opt-in: ordinary mode 1 must not map firmware memory. */
    reset(); arc_run(); assert(!gpu_boot_inventory.arc.requested && map_calls == 2);
    arc_reset(); struct gpu_arc_inventory *a = arc_run();
    assert(map_calls == 4 && !a->error && a->resource[0].count == 4);
    assert(a->resource[0].levels[2] == 128 && a->resource[0].levels[3] == 0);
    assert(a->resource[1].address == 0x30004 && a->resource[2].priority[0] == 4);
    assert(a->resource[0].version == 0x100 && strstr(output, "gfx.lvl hlvl=3 vlvl=0"));
    arc_reset(); fail_locator = 1; a = arc_run(); assert(a->error && map_calls == 3);
    arc_reset(); locator[0] = 0x7ffffffc; a = arc_run(); assert(a->error && map_calls == 3);
    arc_reset(); locator[0] |= 1; a = arc_run(); assert(a->error && map_calls == 3);
    arc_reset(); locator[1] = GPU_DB_HEADER - 4; a = arc_run(); assert(a->error && map_calls == 3);
    arc_reset(); locator[1] = GPU_DB_MAX + 4; a = arc_run(); assert(a->error && map_calls == 3);
    arc_reset(); locator[1]--; a = arc_run(); assert(a->error && map_calls == 3);
    arc_reset(); locator[0] = 0xfffffffcu; a = arc_run(); assert(a->error && map_calls == 3);
    arc_reset(); fail_db = 1; a = arc_run(); assert(a->error && map_calls == 4);
    arc_reset(); db32(4, 0); a = arc_run(); assert(a->error);
    arc_reset(); db32(0, 2); a = arc_run(); assert(a->error);
    arc_reset(); db32(140, 1); a = arc_run(); assert(a->error);
    arc_reset(); db16(10, 1); a = arc_run(); assert(a->error);
    arc_reset(); db16(14, 0xffff); a = arc_run(); assert(a->error);
    arc_reset(); db16(12, 0xffff); a = arc_run(); assert(a->error);
    arc_reset(); db16(8, 0); a = arc_run(); assert(!a->error && !a->resource[0].matches);
    arc_reset(); db16(8, 4); a = arc_run(); assert(!a->error && a->resource[0].error);
    arc_reset(); db32(GPU_DB_HEADER + 16, 0x40000); a = arc_run(); assert(a->resource[0].error);
    arc_reset(); db32(GPU_DB_HEADER + 16, 0x30001); a = arc_run(); assert(a->resource[0].error);
    arc_reset(); db16(GPU_DB_HEADER + 20, 0); a = arc_run(); assert(a->resource[0].error);
    arc_reset(); db16(GPU_DB_HEADER + 20, 3); a = arc_run(); assert(a->resource[0].error);
    arc_reset(); db16(GPU_DB_HEADER + 20, 34); a = arc_run(); assert(a->resource[0].error);
    arc_reset(); db16(GPU_DB_HEADER + 22, 0xffff); a = arc_run(); assert(a->resource[0].error);
    /* An odd auxiliary offset, including a uint16 crossing aligned words. */
    arc_reset(); db16(GPU_DB_HEADER + 22, 1);
    db16(GPU_DB_HEADER + 129, 0); db16(GPU_DB_HEADER + 131, 300);
    db16(GPU_DB_HEADER + 133, 512); db16(GPU_DB_HEADER + 135, 0);
    a = arc_run(); assert(!a->resource[0].error && a->resource[0].levels[1] == 300);
    assert(a->resource[0].levels[2] == 512);
    /* Duplicate identities invalidate the result even if the first was valid.
     * Replay must retain that result without re-reading mutable DB data. */
    arc_reset(); memcpy((char *)database + GPU_DB_HEADER + GPU_DB_ENTRY,
                        database + GPU_DB_HEADER / 4, 8);
    a = arc_run(); assert(a->resource[0].matches == 2 && a->resource[0].error);
    unsigned maps_before = map_calls;
    memset(database, 0xff, sizeof(database)); memset(locator, 0xff, sizeof(locator));
    output[0] = 0; sweet_gpu_replay();
    assert((unsigned)map_calls == maps_before && strstr(output, "duplicate resource"));
    assert(strstr(output, "mx.lvl hlvl=2 vlvl=128"));
    assert(strstr(output, "END boot inventory report 1"));
    arc_reset(); db16(GPU_DB_HEADER + 20, 32);
    for (unsigned k = 0; k < 16; k++) db16(GPU_DB_HEADER + 128 + 2 * k, 48 * k);
    a = arc_run(); assert(!a->resource[0].error && a->resource[0].count == 16);
    assert(a->resource[0].levels[15] == 720);
    arc_reset(); db16(GPU_DB_HEADER + 22, sizeof(database) - 8 - GPU_DB_HEADER - 128);
    db16(sizeof(database) - 8, 0); db16(sizeof(database) - 6, 48);
    db16(sizeof(database) - 4, 300); db16(sizeof(database) - 2, 512);
    a = arc_run(); assert(!a->resource[0].error && a->resource[0].levels[3] == 512);
    arc_reset(); db16(24, 2); a = arc_run();
    assert(a->error && strstr(output, "malformed slave table") && !strstr(output, "hlvl="));
    arc_reset(); a = arc_run(); maps_before = map_calls;
    memset(database, 0xff, sizeof(database)); fail_locator = fail_db = 1;
    output[0] = 0; sweet_gpu_replay();
    assert((unsigned)map_calls == maps_before && strstr(output, "gfx.lvl hlvl=2 vlvl=128"));
    assert(!strstr(output, "ARC skipped") && !strstr(output, "unavailable"));
    /* Deterministic malformed header/entry corpus, also run under ASan/UBSan. */
    uint32_t seed = 0x618;
    for (unsigned k = 0; k < 512; k++) {
        arc_reset();
        seed = seed * 1664525u + 1013904223u;
        unsigned off = (seed >> 8) % 256;
        seed = seed * 1664525u + 1013904223u;
        db16(off, (uint16_t)seed);
        arc_run();
    }
    /* sweetgpu=3: rolled-back CX experiment. */
    arc_reset(); mode = 3; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR;
    arc_run(); struct gpu_power_experiment *x = &gpu_boot_inventory.power;
    assert(x->requested && !x->error && x->enabled && x->disabled);
    assert(vote_count == 4 && !strcmp(vote_name[0], "mx.lvl") && vote_seq[0] == 64);
    assert(!strcmp(vote_name[1], "cx.lvl") && vote_seq[1] == 64);
    assert(!strcmp(vote_name[2], "cx.lvl") && vote_seq[2] == 0);
    assert(!strcmp(vote_name[3], "mx.lvl") && vote_seq[3] == 0);
    assert(x->after_enable & GPU_DOMAIN_ON && x->after_hold & GPU_DOMAIN_ON);
    assert(!(x->after_disable & GPU_DOMAIN_ON) && (cc[GPU_CX_GDSCR / 4] & 1u));
    assert(cc[GPU_CX_GDSCR / 4] == (GPU_CX_IDLE_GDSCR & ~GPU_DOMAIN_ON));
    assert(strstr(output, "CX experiment result: complete, rolled back"));
    output[0] = 0; sweet_gpu_replay(); /* cached, no more votes */
    assert(vote_count == 4 && strstr(output, "CX experiment enable=1"));
    /* Unexpected initial GDSCR: no votes, no writes. */
    arc_reset(); mode = 3; cc[GPU_CX_GDSCR / 4] = 0x80000000u; arc_run();
    assert(vote_count == 0 && gpu_boot_inventory.power.error);
    assert(cc[GPU_CX_GDSCR / 4] == 0x80000000u);
    arc_reset(); mode = 3; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR | GPU_GDSC_HW_CONTROL;
    arc_run(); assert(vote_count == 0 && gpu_boot_inventory.power.error);
    /* ARC inventory failure: not attempted, even with a valid GDSCR. */
    arc_reset(); mode = 3; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; db32(4, 0);
    arc_run(); assert(vote_count == 0 && gpu_boot_inventory.power.error);
    assert(cc[GPU_CX_GDSCR / 4] == GPU_CX_IDLE_GDSCR);
    /* MX vote fails: nothing else touched. */
    arc_reset(); mode = 3; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; vote_fail_on = 1;
    arc_run(); assert(vote_count == 1 && gpu_boot_inventory.power.error);
    assert(cc[GPU_CX_GDSCR / 4] == GPU_CX_IDLE_GDSCR);
    /* CX vote fails: MX is released, GDSCR untouched. */
    arc_reset(); mode = 3; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; vote_fail_on = 2;
    arc_run(); assert(vote_count == 3 && !strcmp(vote_name[2], "mx.lvl") && vote_seq[2] == 0);
    assert(cc[GPU_CX_GDSCR / 4] == GPU_CX_IDLE_GDSCR);
    /* PWR_ON never asserts: still collapsed again and both votes released. */
    arc_reset(); mode = 3; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gdsc_hw_ok = 0;
    arc_run(); x = &gpu_boot_inventory.power;
    assert(!x->enabled && x->error && vote_count == 4 && vote_seq[3] == 0);
    assert(cc[GPU_CX_GDSCR / 4] & 1u);
    /* sweetgpu=4: GMU clock stage runs inside the CX window and undoes itself. */
    arc_reset(); mode = 4; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR;
    uint32_t cmd0 = cc[GPU_GMU_RCG_CMD / 4], cfg0 = cc[GPU_GMU_RCG_CFG / 4];
    arc_run(); x = &gpu_boot_inventory.power;
    assert(x->enabled && x->disabled && !x->error && x->clk_requested && !x->clk_error);
    assert(x->clk_stage == 6 && x->clk_restored);
    assert(x->rcg_cfg1 == ((cfg0 & ~0x71fu) | GPU_GMU_RCG_200MHZ));
    assert(!(x->rcg_cmd1 & GPU_RCG_UPDATE) && (cmd0 & GPU_RCG_UPDATE) == 0);
    for (unsigned i = 0; i < 3; i++) {
        assert(!(x->cbcr_on[i] & GPU_BRANCH_OFF) && (x->cbcr_on[i] & 1u));
    }
    /* Only the branch this code enabled is disabled again. */
    assert((x->cbcr_after[1] & GPU_BRANCH_OFF) && !(x->cbcr_after[1] & 1u));
    assert(cc[GPU_CC_AHB / 4] == 1u && cc[GPU_CC_CXO / 4] == 1u && x->cbcr_after[0] == 0 &&
           x->cbcr_after[2] == 0);
    assert(!(cc[GPU_CC_CX_GMU / 4] & 1u));
    assert((x->cbcr_on[1] & GPU_CBCR_WAKE_SLEEP) == GPU_CBCR_WAKE_SLEEP);
    assert(gcc[GPU_GCC_GPU_GPLL_VOTE / 4] == (1u << 15)); /* gate restored */
    assert(x->gate_on & GPU_GPLL0_DIV_GATE);
    assert(cc[GPU_CX_GDSCR / 4] == (GPU_CX_IDLE_GDSCR & ~GPU_DOMAIN_ON));
    assert(strstr(output, "GMU clk stage=6 restored=1 result: complete, rolled back"));
    /* Gate already set by someone else: left alone on undo. */
    arc_reset(); mode = 4; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR;
    gcc[GPU_GCC_GPU_GPLL_VOTE / 4] |= GPU_GPLL0_DIV_GATE;
    arc_run(); assert(!gpu_boot_inventory.power.clk_error);
    assert(gcc[GPU_GCC_GPU_GPLL_VOTE / 4] & GPU_GPLL0_DIV_GATE);
    /* Preconditions: nothing clock-related written. */
    arc_reset(); mode = 4; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR;
    gcc[GPU_GCC_GPLL0_MODE / 4] = 0;
    arc_run(); x = &gpu_boot_inventory.power;
    assert(x->clk_error && x->clk_stage == 0 && x->enabled && x->disabled);
    assert(gcc[GPU_GCC_GPU_GPLL_VOTE / 4] == (1u << 15) && cc[GPU_GMU_RCG_CFG / 4] == 0x100u);
    arc_reset(); mode = 4; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gcc[GPU_GCC_GPLL0_VOTE / 4] = 0;
    arc_run(); assert(gpu_boot_inventory.power.clk_error && gpu_boot_inventory.power.clk_stage == 0);
    arc_reset(); mode = 4; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; cc[GPU_CC_CX_GMU / 4] = 0x4221u;
    arc_run(); assert(gpu_boot_inventory.power.clk_error && gpu_boot_inventory.power.clk_stage == 0);
    assert(cc[GPU_CC_CX_GMU / 4] == 0x4221u);
    arc_reset(); mode = 4; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; cc[GPU_CC_AHB / 4] = 0x80000001u; clk_stuck = 1;
    arc_run(); assert(gpu_boot_inventory.power.clk_error && gpu_boot_inventory.power.clk_stage == 0);
    assert(cc[GPU_CC_AHB / 4] == 0x80000001u);
    arc_reset(); mode = 4; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; cc[GPU_CC_CXO / 4] = ~0u; clk_stuck = 4;
    arc_run(); assert(gpu_boot_inventory.power.clk_error && gpu_boot_inventory.power.clk_stage == 0);
    /* RCG update never completes: gate undone, no branch enabled. */
    arc_reset(); mode = 4; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; rcg_stuck = 1;
    cc[GPU_GMU_RCG_CMD / 4] = 0x80000001u;
    arc_run(); x = &gpu_boot_inventory.power;
    assert(x->clk_error && x->clk_stage == 2 && x->clk_restored && x->disabled);
    assert(gcc[GPU_GCC_GPU_GPLL_VOTE / 4] == (1u << 15));
    assert(cc[GPU_CC_AHB / 4] == 1u && cc[GPU_CC_CX_GMU / 4] == 0x80004220u);
    /* cx-gmu branch never reports on: it and ahb are disabled again. */
    arc_reset(); mode = 4; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; clk_stuck = 2;
    arc_run(); x = &gpu_boot_inventory.power;
    assert(x->clk_error && x->clk_stage == 4 && x->clk_restored && x->disabled);
    assert(!(cc[GPU_CC_CX_GMU / 4] & 1u) && cc[GPU_CC_AHB / 4] == 1u);
    assert(cc[GPU_CC_CXO / 4] == 1u && gcc[GPU_GCC_GPU_GPLL_VOTE / 4] == (1u << 15));
    /* Mode 4 never touches the GCC bus branches or maps the GMU. */
    arc_reset(); mode = 4; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; arc_run();
    assert(gmu_maps == 0 && gcc[GPU_GCC_MEMNOC_GFX / 4] == 0x80000220u &&
           gcc[GPU_GCC_DDRSS_GPU_AXI / 4] == 0 && !gpu_boot_inventory.power.gmu_mapped);
    /* sweetgpu=5: bus branches on, GMU mapped once, reads cached, all undone. */
    arc_reset(); mode = 5; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; arc_run();
    x = &gpu_boot_inventory.power;
    assert(!x->clk_error && x->clk_stage == 8 && x->clk_restored && x->enabled && x->disabled);
    assert(gmu_maps == 1 && x->gmu_mapped && x->gmu_done == GPU_GMU_READS);
    for (unsigned i = 0; i < GPU_GMU_READS; i++)
        assert(x->gmu_value[i] == (0xa5000000u | (gpu_gmu_regs[i].off / 4)));
    assert(gpu_gmu_regs[0].off == (0x1F800u - 0x1A800u) * 4);
    assert(gpu_gmu_regs[2].off == (0x1F81Cu - 0x1A800u) * 4);
    assert(gpu_gmu_regs[5].off == (0x23B05u - 0x1A800u) * 4);
    assert(!(x->cbcr_on[3] & GPU_BRANCH_OFF) && (x->cbcr_on[3] & 1u) && (x->cbcr_on[4] & 1u));
    assert(gcc[GPU_GCC_MEMNOC_GFX / 4] == 0x80000220u && gcc[GPU_GCC_DDRSS_GPU_AXI / 4] == 0);
    assert(strstr(output, "GMU CM3_FW_INIT_RESULT +0x14070 = 0xa5005")); /* 0x5 01c */
    assert(gcc[GPU_GCC_GPU_GPLL_VOTE / 4] == (1u << 15));
    /* A voted branch someone else already enabled is left enabled. */
    arc_reset(); mode = 5; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR;
    gcc[GPU_GCC_DDRSS_GPU_AXI / 4] = 1;
    arc_run(); assert(!gpu_boot_inventory.power.clk_error && gcc[GPU_GCC_DDRSS_GPU_AXI / 4] == 1);
    /* Mapping failure: no reads, everything undone. */
    arc_reset(); mode = 5; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; fail_gmu_map = 1;
    arc_run(); x = &gpu_boot_inventory.power;
    assert(gmu_maps == 1 && !x->gmu_mapped && x->gmu_done == 0 && x->clk_restored);
    assert(cc[GPU_CC_CX_GMU / 4] == 0x80004ff0u || !(cc[GPU_CC_CX_GMU / 4] & 1u));
    /* No GMU access unless every clock came up. */
    arc_reset(); mode = 5; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; clk_stuck = 2;
    arc_run(); assert(gmu_maps == 0 && gpu_boot_inventory.power.clk_error);
    arc_reset(); mode = 5; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; clk_stuck = 8;
    arc_run(); x = &gpu_boot_inventory.power;
    assert(gmu_maps == 0 && x->clk_error && x->clk_stage == 6 && !(gcc[GPU_GCC_MEMNOC_GFX / 4] & 1u));
    arc_reset(); mode = 5; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gcc[GPU_GCC_GPLL0_MODE / 4] = 0;
    arc_run(); assert(gmu_maps == 0 && gpu_boot_inventory.power.clk_error);
    arc_reset(); mode = 5; cc[GPU_CX_GDSCR / 4] = 0x80000000u; arc_run();
    assert(gmu_maps == 0 && vote_count == 0);
    /* sweetgpu=6: firmware into TCM only while CM3 reset is confirmed. */
    {
        uint32_t fnv = 2166136261u;
        for (unsigned i = 0; i < sizeof(sweet_gpu_gmu_fw); i++)
            fnv = (fnv ^ sweet_gpu_gmu_fw[i]) * 16777619u;
        arc_reset(); mode = 6; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR;
        gmu_mem[0x14000 / 4] = 1;
        uint32_t before[GPU_GMU_SIZE / 4];
        memcpy(before, gmu_mem, sizeof(before));
        arc_run(); x = &gpu_boot_inventory.power;
        assert(!x->clk_error && x->fw_requested && !x->fw_error && x->clk_restored);
        assert(x->fw_size == 0x8000 && x->fw_hash == fnv && x->fw_written == 0x2000 &&
               x->fw_checked == 0x2000 && x->fw_bad == 0);
        for (unsigned i = 0; i < GPU_GMU_SIZE / 4; i++) {
            if (i >= GPU_GMU_TCM / 4 && i < (GPU_GMU_TCM + 0x8000) / 4) {
                const unsigned char *b = &sweet_gpu_gmu_fw[4 * (i - GPU_GMU_TCM / 4)];
                assert(gmu_mem[i] == (uint32_t)(b[0] | b[1] << 8 | b[2] << 16 | (uint32_t)b[3] << 24));
            } else {
                assert(gmu_mem[i] == before[i]); /* nothing outside ITCM/DTCM written */
            }
        }
        assert(strstr(output, "GMU fw result: TCM readback matches; CM3 left in reset"));
        output[0] = 0; sweet_gpu_replay(); /* cached, no new MMIO */
        assert(strstr(output, "GMU fw size=32768") && gmu_maps == 1);
        /* CM3 not in reset (or reset state unknown): nothing is written. */
        for (unsigned bad = 0; bad < 3; bad++) {
            arc_reset(); mode = 6; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR;
            gmu_mem[0x14000 / 4] = bad == 0 ? 0 : bad == 1 ? 3 : ~0u;
            memcpy(before, gmu_mem, sizeof(before));
            arc_run(); x = &gpu_boot_inventory.power;
            assert(x->fw_requested && x->fw_error && x->fw_written == 0);
            assert(!memcmp(before, gmu_mem, sizeof(before)));
        }
        /* Mode 5 never writes the GMU block. */
        arc_reset(); mode = 5; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        memcpy(before, gmu_mem, sizeof(before));
        arc_run(); assert(!gpu_boot_inventory.power.fw_requested && !memcmp(before, gmu_mem, sizeof(before)));
        /* Clock stage failure: GMU never mapped, so nothing written. */
        arc_reset(); mode = 6; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        clk_stuck = 2; memcpy(before, gmu_mem, sizeof(before));
        arc_run(); assert(!gpu_boot_inventory.power.fw_requested && !memcmp(before, gmu_mem, sizeof(before)));
    }
    /* sweetgpu=7: SMMU inventory, read-only, counts bounded by IDR0/IDR1. */
    {
        uint32_t before[GPU_SMMU_SIZE / 4];
        arc_reset(); mode = 7; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        memcpy(before, smmu_mem, sizeof(before));
        arc_run(); x = &gpu_boot_inventory.power;
        assert(!x->clk_error && x->smmu_mapped && smmu_maps == 1 && x->smmu_gr0_done == GPU_SMMU_GR0);
        assert(!memcmp(before, smmu_mem, sizeof(before))); /* no SMMU writes */
        assert(x->smmu_nsmr == 5 && x->smmu_ncb == 3);
        assert(x->smmu_smr[4] == smmu_mem[(GPU_SMMU_SMR + 16) / 4] && x->smmu_smr[5] == 0);
        assert(x->smmu_s2cr[2] == smmu_mem[(GPU_SMMU_S2CR + 8) / 4]);
        assert(x->smmu_cbar[2] == smmu_mem[(GPU_SMMU_CBAR + 8) / 4] && x->smmu_cbar[3] == 0);
        assert(x->smmu_cb[1] == smmu_mem[(GPU_SMMU_CB0 + 0x20) / 4]);
        assert(x->smmu_micro == smmu_mem[GPU_SMMU_MICRO / 4]);
        assert(x->fw_requested && !x->fw_error); /* firmware step still runs first */
        assert(strstr(output, "SMMU IDR1 +0x24 = 0x00000003"));
        output[0] = 0; sweet_gpu_replay(); assert(smmu_maps == 1 && strstr(output, "SMMU SMR4"));
        /* Hostile ID registers cannot push reads past the fixed arrays. */
        arc_reset(); mode = 7; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        smmu_mem[0x20 / 4] = 0xff; smmu_mem[0x24 / 4] = 0xff;
        arc_run(); x = &gpu_boot_inventory.power;
        assert(x->smmu_nsmr == GPU_SMMU_MAXSMR && x->smmu_ncb == GPU_SMMU_MAXCB);
        arc_reset(); mode = 7; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        smmu_mem[0x20 / 4] = smmu_mem[0x24 / 4] = ~0u;
        arc_run(); x = &gpu_boot_inventory.power;
        assert(x->smmu_nsmr == 0 && x->smmu_ncb == 0);
        /* Mapping failure, and modes below 7 never map the SMMU. */
        arc_reset(); mode = 7; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        fail_smmu_map = 1; arc_run();
        assert(smmu_maps == 1 && !gpu_boot_inventory.power.smmu_mapped);
        arc_reset(); mode = 6; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        arc_run(); assert(smmu_maps == 0);
        /* No SMMU access unless every clock came up. */
        arc_reset(); mode = 7; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        clk_stuck = 8; arc_run(); assert(smmu_maps == 0 && gpu_boot_inventory.power.clk_error);
    }
    /* sweetgpu=8: GMU stream context bank + ATOS check, fully restored. */
    {
        const unsigned cb = GPU_SMMU_CB0 + 3 * 0x1000;
#define SMMU_DEFAULTS() do { \
        smmu_mem[0x20 / 4] = 5; smmu_mem[0x24 / 4] = 5; smmu_mem[0 / 4] = 0x00200626u; \
        smmu_mem[(GPU_SMMU_SMR + 12) / 4] = 0; smmu_mem[(GPU_SMMU_S2CR + 12) / 4] = GPU_SMMU_S2CR_FAULT; \
        smmu_mem[(GPU_SMMU_CBAR + 12) / 4] = 0; smmu_mem[(GPU_SMMU_CBA2R + 12) / 4] = 0; \
        for (unsigned o = 0; o < 0x1000; o += 4) smmu_mem[(cb + o) / 4] = 0; \
        last_ats = 0; } while (0)
        uint32_t before[GPU_SMMU_SIZE / 4];
        arc_reset(); mode = 8; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        SMMU_DEFAULTS();
        memcpy(before, smmu_mem, sizeof(before));
        arc_run(); x = &gpu_boot_inventory.power;
        assert(!x->ctx_error && x->ctx_requested && x->ctx_passed == 4 && x->ctx_restored);
        assert(alloc_calls == 1 && clean_calls == 1 && x->ctx_pa == 0x90000000ull);
        assert(x->ctx_ttbr == x->ctx_pa && x->ctx_pte3 == ((x->ctx_pa + 0x3000) | GPU_PTE_PAGE));
        assert(dma_rd64(fake_pa_base) == 0 && dma_rd64(fake_pa_base + 8) == ((x->ctx_pa + 0x1000) | 3));
        assert(dma_rd64(fake_pa_base + 0x1000 + 8 * 256) == ((x->ctx_pa + 0x2000) | 3));
        assert(dma_rd64(fake_pa_base + 0x2000) == x->ctx_pte3);
        assert((x->ctx_par[0] & 0x0000fffffffff000ull) == x->ctx_pa + 0x3000 && !(x->ctx_par[0] & 1));
        assert((x->ctx_par[1] & 0x0000fffffffff000ull) == x->ctx_pa + 0x3000 && (x->ctx_par[2] & 1) && (x->ctx_par[3] & 1));
        for (unsigned i = 0; i < GPU_SMMU_SIZE / 4; i++) {
            if (i >= cb / 4 && i < (cb + 0x1000) / 4) continue; /* ATOS/TLB scratch in CB3 only */
            assert(smmu_mem[i] == before[i]);
        }
        assert(smmu_mem[cb / 4] == 0 && smmu_rd64(cb + GPU_SMMU_CB_TTBR0) == 0 &&
               smmu_mem[(cb + GPU_SMMU_CB_TCR) / 4] == 0 && smmu_mem[(cb + GPU_SMMU_CB_MAIR0) / 4] == 0);
        assert(strstr(output, "SMMU ctx result: all translations as expected, restored"));
        output[0] = 0; sweet_gpu_replay(); assert(alloc_calls == 1 && strstr(output, "SMMU ctx ATOS va=0x60000000"));
        /* Pre-state not the ABL default (or unsuitable geometry): nothing is written or allocated. */
        for (unsigned bad = 0; bad < 8; bad++) {
            arc_reset(); mode = 8; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
            SMMU_DEFAULTS();
            switch (bad) {
            case 0: smmu_mem[(GPU_SMMU_SMR + 12) / 4] = 0x80000005u; break;
            case 1: smmu_mem[(GPU_SMMU_S2CR + 12) / 4] = 1; break;
            case 2: smmu_mem[(GPU_SMMU_CBAR + 12) / 4] = 1u << 16; break;
            case 3: smmu_mem[(GPU_SMMU_CBA2R + 12) / 4] = 1; break;
            case 4: smmu_mem[cb / 4] = 1; break;
            case 5: smmu_mem[0] |= 1u; break;           /* CLIENTPD */
            case 6: smmu_mem[0x24 / 4] = 3; break;      /* NUMCB too small */
            case 7: smmu_mem[0x20 / 4] = 3; break;      /* NUMSMRG too small */
            }
            memcpy(before, smmu_mem, sizeof(before));
            arc_run(); x = &gpu_boot_inventory.power;
            assert(x->ctx_requested && x->ctx_error && alloc_calls == 0 && x->ctx_stage == 0);
            assert(!memcmp(before, smmu_mem, sizeof(before)));
        }
        /* No memory: nothing written. */
        arc_reset(); mode = 8; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        SMMU_DEFAULTS(); fail_alloc = 1; memcpy(before, smmu_mem, sizeof(before));
        arc_run(); assert(gpu_boot_inventory.power.ctx_error && !memcmp(before, smmu_mem, sizeof(before)));
        /* Page outside the 36-bit output range: refused before any SMMU write. */
        arc_reset(); mode = 8; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        SMMU_DEFAULTS(); fake_pa_base = 1ull << 36; memcpy(before, smmu_mem, sizeof(before));
        arc_run(); assert(gpu_boot_inventory.power.ctx_error && !memcmp(before, smmu_mem, sizeof(before)));
        /* ATOS never finishes: reported, and the SMMU is still restored. */
        arc_reset(); mode = 8; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        SMMU_DEFAULTS(); ats_stuck = 1;
        arc_run(); x = &gpu_boot_inventory.power;
        assert(x->ctx_error && x->ctx_passed == 0 && x->ctx_restored && smmu_mem[(GPU_SMMU_SMR + 12) / 4] == 0);
        /* Modes 7 and below never allocate or write the SMMU. */
        arc_reset(); mode = 7; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        SMMU_DEFAULTS(); memcpy(before, smmu_mem, sizeof(before));
        arc_run(); assert(alloc_calls == 0 && !gpu_boot_inventory.power.ctx_requested &&
                          !memcmp(before, smmu_mem, sizeof(before)));
    }
    /* Mode 3 never runs the clock stage. */
    arc_reset(); mode = 3; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; arc_run();
    assert(!gpu_boot_inventory.power.clk_requested);
    assert(cc[GPU_CC_CX_GMU / 4] == 0x80004220u && cc[GPU_GMU_RCG_CFG / 4] == 0x100u);
    /* Mode 2 never reaches the experiment. */
    arc_reset(); cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; arc_run();
    assert(!gpu_boot_inventory.power.requested && vote_count == 0 && delay_calls == 0);
    puts("PASS: 14 clock/cache cases, 30 ARC cases + 512 mutations, 47 CX experiment cases");
    return 0;
}
'''


if __name__ == '__main__':
    unittest.main()
