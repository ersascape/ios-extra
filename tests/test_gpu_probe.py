"""Exercise the actual patch's opt-in and MMIO mapping boundaries on the host.

Only the ARM memory-barrier instruction is replaced for host execution.
The real source is also cross-compiled separately against XNU headers.
"""
from pathlib import Path
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
            self.assertEqual(source.count(barrier), 1)
            (work / 'sweet_gpu.c').write_text(source.replace(
                barrier, '__asm__ volatile("" ::: "memory");'))
            headers = {
                'sys/param.h': '#include <stdint.h>\ntypedef uintptr_t vm_offset_t;\n'
                               'typedef uintptr_t vm_size_t;\n',
                'sys/systm.h': '',
                'pexpert/pexpert.h': 'int PE_parse_boot_argn(const char *, void *, int);\n',
            }
            for name, text in headers.items():
                path = work / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            (work / 'test.c').write_text(HARNESS)
            subprocess.run([shutil.which('cc') or 'cc', '-std=c11', '-Wall',
                            '-Wextra', '-Werror', '-I', str(work),
                            str(work / 'test.c'), '-o', str(work / 'test')], check=True)
            result = subprocess.run([str(work / 'test')], capture_output=True,
                                    text=True, check=True)
            self.assertIn('PASS: 14 clock/cache cases, 30 ARC cases + 512 mutations', result.stdout)


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
static int fail_locator, fail_db;
static char output[65536];

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
    reset(); mode = 3; sweet_gpu_probe(); assert(map_calls == 0);
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
    puts("PASS: 14 clock/cache cases, 30 ARC cases + 512 mutations");
    return 0;
}
'''


if __name__ == '__main__':
    unittest.main()
