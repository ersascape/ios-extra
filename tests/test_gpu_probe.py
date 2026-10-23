"""Exercise the actual patch's opt-in and MMIO mapping boundaries on the host.

ARM barriers and explicit masks are replaced for host execution; MMIO stores
are hooked for modeled readbacks and write-count assertions.
The real source is also cross-compiled separately against XNU headers.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def added_header(patch_path, header_path):
    text = patch_path.read_text()
    marker = f'+++ b/{header_path}\n'
    section = text.split(marker, 1)[1].split('\ndiff --git ', 1)[0]
    return '\n'.join(line[1:] for line in section.splitlines()
                      if line.startswith('+') and not line.startswith('+++')) + '\n'


class GPUProbeTests(unittest.TestCase):
    def test_mmio_boundaries(self):
        with tempfile.TemporaryDirectory(prefix='ios-extra-gpu-test-') as directory:
            work = Path(directory)
            for patch in sorted((ROOT / 'xnu/patches').glob('*.patch')):
                if b'+++ b/bsd/dev/sweet_gpu.c\n' in patch.read_bytes():
                    subprocess.run(['git', 'apply', '--include=bsd/dev/sweet_gpu.c',
                                    str(patch)], cwd=work, check=True)
            source = (work / 'bsd/dev/sweet_gpu.c').read_text()
            self.assertIn('FP6_REPLAY_CHECK_GRID', source,
                          'scene renders must be compared with their lavapipe reference grids')
            self.assertIn('PE_parse_boot_argn("fp6gpuexec"', source,
                          'SQE/CP execution must remain explicitly opt-in')
            self.assertIn('fp6_hfi_hdr(131u, cmd_dwords + 1u)', source,
                          'raw CP packets must use the Gen8 HFI raw-command message')
            self.assertIn('fp6_cp_type7_packet(0x3du, 3u)', source,
                          'write/readback probe must use CP_MEM_WRITE')
            self.assertIn('fp6_gpu_exec_alloc_sqe()', source,
                          'SQE must be backed pagewise for a contiguous GPU VA')
            self.assertIn('fp6_exec_sqe[i].pa, FP6_GPU_GLOBAL_GFX_EXEC))', source,
                          'SQE pages must be executable and accessible to unprivileged GPU reads')
            self.assertNotIn('fp6_exec_sqe[i].pa, FP6_HFI_MEMFLAG_GFX_PRIV', source,
                             'SQE firmware must not be mapped privileged-only')
            self.assertIn('FP6_GPU_GLOBAL_GFX_EXEC', source,
                          'SQE firmware pages must be executable in the GPU SMMU')
            self.assertIn('FP6_GPU_CP_APRIV_CNTL_PIPE    0x2134u', source,
                          'CP_APRIV_CNTL_PIPE must be programmed as in Linux gen8_start()')
            self.assertIn('FP6_GPU_BR_APRIV_DEFAULT      0x6fu', source,
                          'BR pipe also marks crashdumper accesses privileged')
            self.assertLess(source.index('\tfp6_gpu_program_apriv(gpu);\n'),
                            source.index('fp6_smmu_write32(gpu, 0x2058u, (uint32_t)fp6_exec_sqe_va)'),
                            'APRIV must be programmed before the SQE base and start')
            self.assertIn('flags & (FP6_GPU_GLOBAL_GFX_PRIV | FP6_GPU_GLOBAL_GFX_WRITE)', source,
                          'HFI GMU_ACC (bit 3) must not become GPU EXEC in the global map')
            self.assertIn('FP6_GPU_UCHE_TRAP_BASE 0x0001fffffffff000ULL', source,
                          'UCHE trap base must match Linux gen8_get_uche_trap_base()')
            self.assertLess(source.index('\tfp6_gpu_program_uche(gpu);\n'),
                            source.index('fp6_smmu_write32(gpu, 0x2058u, (uint32_t)fp6_exec_sqe_va)'),
                            'UCHE bases must be programmed before SQE start')
            self.assertIn('fp6_gpu_nonctxt_regs[]', source,
                          'A810 non-context register table must be present')
            self.assertEqual(source.count('/* RB_GC_GMEM_PROTECT */'), 1)
            self.assertNotIn('CP_SMMU_STREAM_ID_LPAC', source.split('fp6_gpu_nonctxt_regs[] = {')[1].split('};')[0],
                             'LPAC is not enabled on A810')
            self.assertLess(source.index('\tfp6_gpu_program_nonctxt(gpu);\n'),
                            source.index('fp6_smmu_write32(gpu, 0x2058u, (uint32_t)fp6_exec_sqe_va)'),
                            'non-context registers must be programmed before SQE start')
            self.assertIn('PE_parse_boot_argn("fp6gpuring"', source,
                          'host ring write must remain explicitly opt-in')
            self.assertIn('FP6_GMU_AHB_FENCE_STATUS 0x57c4cu', source,
                          'CP_RB_WPTR must be written through the AHB fence check')
            self.assertIn('fp6_hfi_mem_allocs[i].mem_kind == 1u', source,
                          'host ring write must target a firmware kind-1 ring only')
            self.assertIn('PE_parse_boot_argn("fp6gpucompute"', source,
                          'compute dispatch must remain explicitly opt-in')
            self.assertIn('fp6_cp_type7_packet(0x1fu, 1u); /* CP_RESET_CONTEXT_STATE */', source,
                          'replay must clear BV/BR counters like the Linux gen8 submit path')
            self.assertIn('video.v_baseAddr != FP6_SCANOUT_PA', source,
                          'scanout mapping must verify the exact ADT framebuffer geometry first')
            self.assertIn('#define FP6_SCANOUT_PA 0xe3940000ull', source,
                          'scanout base must be the ADT / upstream FP6 simple-framebuffer address')
            self.assertIn('PE_parse_boot_argn("fp6gpuscanoutread"', source,
                          'the framebuffer CPU readback must be opt-in after it lost a boot log')
            self.assertIn('PE_parse_boot_argn("fp6dpusnap"', source,
                          'the display snapshot must be explicitly opt-in')
            dpu_start = source.index('fp6_dpu_snapshot(void)\n{')
            dpu = source[dpu_start:source.index('fp6_smmu_inventory(void)\n{', dpu_start)]
            self.assertNotRegex(dpu, r'fp6_smmu_write(32|64)\(',
                                'the display snapshot must not write any register')
            self.assertIn('if (level >= 3)', dpu, 'refresh sampling is its own opt-in level')
            self.assertNotIn('smmu_write', dpu, 'the display probe must stay read-only at every level')
            self.assertLess(dpu.index('GDSCR'), dpu.index('FP6_MDSS_PA, FP6_MDSS_SIZE'),
                            'the MDSS power domain must be checked before the MDP block is mapped')
            self.assertIn('PE_parse_boot_argn("fp6gpuscanout"', source,
                          'writing into the display framebuffer must be explicitly opt-in')
            self.assertIn('PE_parse_boot_argn("fp6gpureplaycb"', source,
                          'clearing CONCURRENT_BIN_DISABLE must be explicitly opt-in')
            self.assertIn('PE_parse_boot_argn("fp6gpureplaystep"', source,
                          'prefix bisection must be explicitly opt-in')
            self.assertIn('PE_parse_boot_argn("fp6gpureplay"', source,
                          'TTBR0 capture replay must remain explicitly opt-in')
            self.assertIn('#define FP6_AS_TCR_TTBR0 0xa0102010u', source,
                          'TTBR0 enable must keep the TTBR1 half of the live TCR unchanged')
            self.assertIn('FP6_AS_PTE_PAGE (3ull | (1ull << 10) | (2ull << 8) | (1ull << 11) | (1ull << 6) | (3ull << 53))',
                          source, 'replay pages must be unprivileged read/write and execute-never')
            self.assertLess(source.index('(void)fp6_gpu_compute_probe(g, gpu);'),
                            source.index('(void)fp6_gpu_replay_probe(g, gpu);'),
                            'replay follows the proven compute probe')
            self.assertIn('wanted < 1 || wanted > 16', source,
                          'repeat count must be bounded')
            self.assertIn('test->data[i] + 5u * iteration', source,
                          'each repeat must verify the accumulated result')
            self.assertIn('fp6_cs_patch(stream, test->reloc[2]', source,
                          'every pointer operand in the stream, including the event scratch, must be relocated')
            self.assertIn('fp6_cs_patch(stream, test->reloc[3]', source,
                          'Mesa shim IOVAs must be relocated, including the completion fence')
            self.assertIn('(uint64_t)wptr + total >= size', source,
                          'compute stream must not wrap the firmware ring')
            self.assertLess(source.index('(void)fp6_gpu_ring_probe(g, gpu);'),
                            source.index('(void)fp6_gpu_compute_probe(g, gpu);'),
                            'compute dispatch follows the proven host-ring probe')
            self.assertIn('va != fp6_exec_sqe_va + (uint64_t)i * 4096u', source,
                          'SQE pages must form one contiguous GPU virtual range')
            self.assertLess(
                source.index('HFI START ACK; core firmware initialized'),
                source.index('if (!fp6_gmu_hfi_default_votes('),
                'Linux default DCVS votes must follow the HFI START ACK')
            self.assertLess(
                source.index('if (!fp6_gmu_hfi_default_votes('),
                source.index('!fp6_gmu_gpu_oob('),
                'Linux default DCVS votes must precede the GPU OOB request')
            self.assertIn('fp6_smmu_write32(g, 0x4764cu, 0x7fffffffu);', source,
                          'the OOB ACK interrupt must remain unmasked during polling')
            self.assertIn('fp6_gpu_exec_snapshot(g, gpu, "after-cp-init")', source,
                          'CP init must be followed by a read-only fault snapshot')
            self.assertIn('fp6_gpu_exec_snapshot(g, gpu, "after-secure-trust")', source,
                          'secure-trust transition must be followed by a read-only snapshot')
            self.assertIn('CBFRSYNRA0=', source,
                          'fault attribution must include the selected SMMU context bank SID')
            self.assertIn('CBFRSYNRA4=', source,
                          'fault attribution must include context bank 4 reported by FSYNR0')
            self.assertIn('walk root=', source,
                          'fault report must include the actual TTBR1 descriptors and SQE leaf PTE')
            self.assertIn('CB%u CBAR=', source,
                          'fault report must compare CB0 with CB4 configuration and syndrome')
            for offset in ('0x57c34u', '0x57c38u', '0x1a8u', '0x22d4u',
                           '0x2088u', '0x22ecu', 'FP6_SMMU_CB_FSR',
                           '0x0060u', '0x0068u', '0x006cu'):
                self.assertIn(offset, source,
                              f'GPU fault snapshot must include {offset}')
            self.assertIn('fp6_smmu_read64(smmu, fp6_gpu_cb_off + 0x0060u)', source,
                          'SMMU FAR must be captured at full physical-address width')
            self.assertLess(source.index('"after-cp-init"'),
                            source.index('"after-secure-trust"'),
                            'snapshot ordering must isolate the secure-trust transition')
            source = source.replace('__asm__ volatile("dsb sy" ::: "memory");', '')
            source = source.replace('__asm__ volatile("dc ivac, %0" :: "r"(p) : "memory");', '(void)p;')
            for name in ('fp6_gmu_loader.h',):
                shutil.copyfile(ROOT / 'xnu/helpers' / name, work / name)
            domain_patch = (ROOT / 'xnu/patches/0133-fp6-gmu-persistent-domain.patch').read_text()
            domain_header = '\n'.join(line[1:] for line in domain_patch.splitlines()
                                       if line.startswith('+') and not line.startswith('+++'))
            patch_0163 = ROOT / 'xnu/patches/0163-fp6-gpu-global-domain.patch'
            domain_dir = work / 'bsd/dev'
            domain_dir.mkdir(parents=True, exist_ok=True)
            (domain_dir / 'fp6_gpu_global_domain.h').write_text(
                added_header(patch_0163, 'bsd/dev/fp6_gpu_global_domain.h'))
            (domain_dir / 'fp6_gmu_domain.h').write_text(domain_header)
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gmu_domain.h',
                            str(patch_0163)], cwd=work, check=True)
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gpu_global_domain.h',
                            str(ROOT / 'xnu/patches/0185-fp6-sqe-executable-mapping.patch')],
                           cwd=work, check=True)
            shutil.copyfile(domain_dir / 'fp6_gpu_global_domain.h',
                            work / 'fp6_gpu_global_domain.h')
            shutil.copyfile(domain_dir / 'fp6_gmu_domain.h', work / 'fp6_gmu_domain.h')
            (work / 'fp6_gmu_fw.h').write_text(
                'struct fp6_gmu_fw_preallocation { uint32_t address,size,type; };\n'
                'struct fp6_gmu_fw_block { uint32_t address,size,type,value; const uint8_t *data; };\n'
                '#define FP6_GMU_FW_PREALLOCATION_COUNT 1u\n#define FP6_GMU_FW_BLOCK_COUNT 1u\n'
                'static const uint8_t payload[4] = {1,2,3,4};\n'
                'static const struct fp6_gmu_fw_preallocation fp6_gmu_fw_preallocations[]={{0x60000000,4096,1}};\n'
                'static const struct fp6_gmu_fw_block fp6_gmu_fw_blocks[]={{0x60000000,4,0xefbeadde,0xefbeadde,payload}};\n')
            barrier = '__asm__ volatile("dmb oshld" ::: "memory");'
            self.assertEqual(source.count(barrier), 4)  # SWEET 32/64-bit + FP6 GPUCC/SMMU barriers
            for name in ('dmb oshld', 'dmb oshst', 'dsb osh'):
                text = '__asm__ volatile("%s" ::: "memory");' % name
                self.assertEqual(source.count(text), 4)
                source = source.replace(text, '__asm__ volatile("" ::: "memory");')
            # FP6 accessors are single LDR/STR inline asm (hypervisor-trap safe);
            # model them as plain host loads and the same store hooks.
            asm_load32 = '__asm__ volatile("ldr %w0, [%1]" : "=r"(value) : "r"(base + off) : "memory");'
            self.assertEqual(source.count(asm_load32), 2)
            source = source.replace(asm_load32, 'value = *(volatile uint32_t *)(base + off);')
            asm_store32 = '__asm__ volatile("str %w0, [%1]" : : "r"(value), "r"(base + off) : "memory");'
            self.assertEqual(source.count(asm_store32), 1)
            source = source.replace(asm_store32, 'test_store32(base, off, value);')
            asm_store64 = '__asm__ volatile("str %x0, [%1]" : : "r"(value), "r"(base + off) : "memory");'
            self.assertEqual(source.count(asm_store64), 1)
            source = source.replace(asm_store64, 'test_store64(base, off, value);')
            store32 = '*(volatile uint32_t *)(base + off) = value;'
            self.assertEqual(source.count(store32), 1)
            source = source.replace(store32, 'test_store32(base, off, value);')
            mask = '__asm__ volatile("and %0, %0, #0xffffffff" : "+r" (got));'
            self.assertEqual(source.count(mask), 1)
            source = source.replace(mask, 'got &= 0xffffffffULL;')
            narrow_input = '__asm__ volatile("and %0, %0, #0xffffffff" : "+r" (value));'
            self.assertEqual(source.count(narrow_input), 1)
            source = source.replace(narrow_input, 'value &= 0xffffffffULL;')
            store64 = '*(volatile uint64_t *)(base + off) = value;'
            self.assertEqual(source.count(store64), 1)
            source = source.replace(store64, 'test_store64(base, off, value);')
            (work / 'sweet_gpu.c').write_text(source)
            headers = {
                'sys/param.h': '#include <stdint.h>\ntypedef uintptr_t vm_offset_t;\n'
                               'typedef uintptr_t vm_size_t;\n',
                'sys/systm.h': '',
                'kern/clock.h': 'void delay(int);\n',
                'kern/startup.h': '#define __startup_func\n#define STARTUP(phase, rank, fn) '
                                  'static void (* const startup_test_ref_##fn)(void) '
                                  '__attribute__((used)) = fn;\n#define EARLY_BOOT 1\n'
                                  '#define STARTUP_RANK_LAST 4\n',
                'arm/caches_internal.h': '#define TRUE 1\ntypedef unsigned long long addr64_t;\n'
                                         'void clean_dcache64(addr64_t, unsigned, int);\n'
                                         'void flush_dcache64(addr64_t, unsigned, int);\n',
                'arm/machine_routines.h': 'typedef int boolean_t;\n#define FALSE 0\n'
                                          'boolean_t ml_set_interrupts_enabled(boolean_t);\n',
                'vm/pmap.h': '#include <vm/memory_types.h>\ntypedef unsigned long long addr64_t;\ntypedef unsigned int ppnum_t;\n'
                             'typedef void *pmap_t;\nextern pmap_t kernel_pmap;\n'
                             '#define ptoa_64(x) ((unsigned long long)(x) << 14)\n'
                             'extern ppnum_t pmap_find_phys(pmap_t, addr64_t);\n'
                             'extern unsigned int pmap_cache_attributes(ppnum_t);\n'
                             'extern void pmap_set_cache_attributes(ppnum_t, unsigned int);\n',
                'vm/memory_types.h': '#define VM_WIMG_MASK 0xffu\n#define VM_WIMG_DEFAULT 0x2u\n#define VM_WIMG_WCOMB 0x6u\n',
                'vm/vm_kern.h': 'typedef int kern_return_t;\ntypedef void *vm_map_t;\n'
                                'extern vm_map_t kernel_map;\n#define KERN_SUCCESS 0\n'
                                '#define PAGE_SIZE 0x4000UL\n#define PAGE_MASK 0x3fffUL\n#define KMA_DATA 1\n#define KMA_ZERO 2\n'
                                '#define KMA_PERMANENT 4\n#define VM_KERN_MEMORY_IOKIT 0\n'
                                'kern_return_t kmem_alloc_contig(vm_map_t, vm_offset_t *, vm_size_t, '
                                'vm_offset_t, unsigned, unsigned, unsigned, int);\n',
                'pexpert/pexpert.h': '#ifndef PEXPERT_STUB_H\n#define PEXPERT_STUB_H\n'
                                     'int PE_parse_boot_argn(const char *, void *, int);\n'
                                     'typedef struct PE_Video { unsigned long v_baseAddr, v_rowBytes, '
                                     'v_width, v_height, v_depth; } PE_Video;\n'
                                     'int PE_current_console(PE_Video *);\n#endif\n',
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
            (work / 'fp6_zap_fw.h').write_text(
                'static const unsigned char fp6_zap_metadata[0xfcc] = {1,2,3};\n'
                'static const unsigned char fp6_zap_segment[0x378] = {4,5,6};\n')
            (work / 'fp6_sqe_fw.h').write_text(
                '#define FP6_SQE_FW_VERSION 0x01100067u\n'
                '#define FP6_SQE_FW_SIZE 16u\n'
                'static const unsigned char fp6_sqe_fw[FP6_SQE_FW_SIZE] = {0};\n')
            (work / 'fp6_gpu_compute_tests.h').write_text(added_header(
                ROOT / 'xnu/patches/0197-fp6-compute-multi-kernel-batch.patch',
                'bsd/dev/fp6_gpu_compute_tests.h'))
            replay_dir = work / 'replay' / 'bsd' / 'dev'
            replay_dir.mkdir(parents=True)
            (replay_dir / 'fp6_gpu_replay_data.h').write_text(added_header(
                ROOT / 'xnu/patches/0198-fp6-ttbr0-capture-replay.patch',
                'bsd/dev/fp6_gpu_replay_data.h'))
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gpu_replay_data.h',
                            str(ROOT / 'xnu/patches/0200-fp6-replay-prefix-bisection.patch')],
                           cwd=work / 'replay', check=True)
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gpu_replay_data.h',
                            str(ROOT / 'xnu/patches/0204-fp6-replay-clear-concurrent-bin-disable.patch')],
                           cwd=work / 'replay', check=True)
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gpu_replay_data.h',
                            str(ROOT / 'xnu/patches/0206-fp6-replay-scanout-framebuffer.patch')],
                           cwd=work / 'replay', check=True)
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gpu_replay_data.h',
                            str(ROOT / 'xnu/patches/0211-fp6-replay-scene-grid-check.patch')],
                           cwd=work / 'replay', check=True)
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gpu_replay_data.h',
                            str(ROOT / 'xnu/patches/0212-fp6-replay-scene-diagnostics.patch')],
                           cwd=work / 'replay', check=True)
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gpu_replay_data.h',
                            str(ROOT / 'xnu/patches/0215-fp6-replay-scenes-fit-576k-gmem.patch')],
                           cwd=work / 'replay', check=True)
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gpu_replay_data.h',
                            str(ROOT / 'xnu/patches/0216-fp6-replay-selection-and-texdouble.patch')],
                           cwd=work / 'replay', check=True)
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gpu_replay_data.h',
                            str(ROOT / 'xnu/patches/0217-fp6-replay-texture-without-descriptor-prefetch.patch')],
                           cwd=work / 'replay', check=True)
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gpu_replay_data.h',
                            str(ROOT / 'xnu/patches/0218-fp6-replay-texture-variant-batch.patch')],
                           cwd=work / 'replay', check=True)
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gpu_replay_data.h',
                            str(ROOT / 'xnu/patches/0219-fp6-replay-flush-variants.patch')],
                           cwd=work / 'replay', check=True)
            subprocess.run(['git', 'apply', '--include=bsd/dev/fp6_gpu_replay_data.h',
                            str(ROOT / 'xnu/patches/0220-fp6-replay-post-draw-flush-variants.patch')],
                           cwd=work / 'replay', check=True)
            shutil.copyfile(replay_dir / 'fp6_gpu_replay_data.h', work / 'fp6_gpu_replay_data.h')
            (work / 'test.c').write_text(HARNESS)
            build = subprocess.run([shutil.which('cc') or 'cc', '-std=c11', '-Wall',
                                    '-Wextra', '-Werror', *os.environ.get('IOS_EXTRA_CFLAGS', '').split(), '-I', str(work),
                                    str(work / 'test.c'), '-o', str(work / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run([str(work / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS: interrupt mask/restore', result.stdout)
            self.assertIn('PASS: six IRQ/fence reads', result.stdout)
            self.assertIn('PASS: RSC wake/stop', result.stdout)
            self.assertIn('PASS: 29 pre-boot registers', result.stdout)
            self.assertIn('PASS: GMU buffers 29 ATOS checks', result.stdout)
            self.assertIn('PASS: GPU SID0 TTBR1 setup replaces only stale disabled CB0', result.stdout)
            self.assertIn('PASS: HFI GFX_ACC allocation returns a live GPU TTBR1 mapping', result.stdout)
            self.assertIn('PASS: HFI GET_VALUE and one-dword START share the bounded queue dispatcher', result.stdout)
            self.assertIn('PASS: opt-in HFI no-preemption omits only the feature command; default A810 request remains intact', result.stdout)
            self.assertIn('PASS: 14 clock/cache cases, 30 ARC cases + 512 mutations, 61 CX experiment cases', result.stdout)
            self.assertIn('PASS: FP6 GPUCC inventory is opt-in, read-only, and bounded', result.stdout)
            self.assertIn('PASS: FP6 Qualcomm SCM PAS query is opt-in and never authenticates firmware', result.stdout)
            self.assertIn('PASS: FP6 signed ZAP PAS load is opt-in, stage-ordered, and shuts down on failure', result.stdout)
            self.assertIn('PASS: FP6 SMMU global IRQ inventory is opt-in, read-only, and bounded', result.stdout)
            self.assertIn('PASS: FP6 Adreno work starts from its dedicated EARLY_BOOT hook', result.stdout)


HARNESS = r'''
#include <assert.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <sys/param.h>
static void test_store32(vm_offset_t base, uint32_t off, uint32_t value);
static void test_store64(vm_offset_t base, uint32_t off, uint64_t value);
static int probe_printf(const char *, ...);
#define printf probe_printf
#define ARM64_BOARD_CONFIG_SWEET 1
#define ARM64_BOARD_CONFIG_FP6 1
#define FP6_SCM_TEST 1
#define FP6_GMU_TEST 1
#include "sweet_gpu.c"
#undef printf

uint64_t fp6_gmu_test_counter(void) { static uint64_t ticks=1000000; return ticks+=20; }
uint64_t fp6_gmu_test_frequency(void) { return 19200000; }
boolean_t ml_set_interrupts_enabled(boolean_t enable) { static boolean_t old=1; boolean_t v=old; old=enable; return v; }

static uint32_t gcc[0x90000 / 4], cc[0x9000 / 4];
static uint32_t fp6_gpucc[0x9800 / 4], fp6_gpucc_before[0x9800 / 4];
static uint32_t fp6_smmu[0x40000 / 4];
static uint32_t fp6_gicd[0x10000 / 4];
static uint32_t fp6_gcc_gpu[0x1000 / 4];
static uint32_t fp6_gmu_regs[0x68000/4], fp6_gcc_pll[0x1000/4], fp6_gcc_votes[0x1000/4];
static uint8_t *hfi_fake_mem;
static uint32_t hfi_fake_result;
static int hfi_fake_enabled;
static int fp6_gmu_clock_model, fp6_root_stuck, fp6_fail_pll_map;
static int fp6_clock_refuse = -1;
static int fp6_power_mode, fp6_gmu_no_preempt_mode;
static uint32_t fp6_rsc[0x10000 / 4], fp6_cmd_db[0x20000 / 4];
#define FP6_TEST_CB 2u
#define FP6_TEST_CB_BASE 0x22000u
static unsigned fp6_ats64_writes;
static uint32_t fp6_refuse_off; static unsigned fp6_refuse_nth, fp6_refuse_count;
static uint32_t fp6_seen_tcr2, fp6_seen_cbar, fp6_seen_fsr_clear;
static int fp6_gpu_smmu_model, global_alloc_mode;
static size_t global_alloc_offset;
static int present, mode, map_calls, fail_gcc, fail_cc;
static int fp6_mode, fp6_smmu_mode;
static unsigned fp6_map_calls, fp6_smmu_maps;
static int fp6_pas_mode;
static int fp6_zap_mode, zap_map_fail;
static int fp6_smmu_irq_mode, fail_fp6_gicd_map;
static unsigned fp6_gicd_maps;
static uint64_t scm_status[2], scm_value[2], scm_fid[2], scm_arginfo[2], scm_arg0[2];
static unsigned scm_calls;
static struct { uint64_t fid, arginfo, arg0, arg1, arg2, status, value; } scm_full[8];
static unsigned scm_full_calls, scm_full_fail_at;
static unsigned char zap_region[0x2000];
static uint32_t locator[2], database[1024];
static uint32_t gmu_mem[GPU_GMU_SIZE / 4];
static int gmu_maps, fail_gmu_map;
/* Fake DMA page, SMMU ATOS model and cache-clean counters (sweetgpu=8). */
static unsigned char dma_block[0x40000] __attribute__((aligned(16384)));
static unsigned long long fake_pa_base;
static int fail_alloc, alloc_calls, clean_calls, ats_stuck, tlb_stuck;
static uint64_t last_ats, fp6_last_ats;
static int alloc_null, alloc_unaligned, phys_discontig, bad_atos, smmu_write_calls, all_mmio_writes;
static uint32_t refuse_smmu_off;
static unsigned refused_writes;
static unsigned clean_bytes;
pmap_t kernel_pmap; vm_map_t kernel_map;
static uint32_t smmu_mem[GPU_SMMU_SIZE / 4];
static uint32_t pdc_mem[GPU_PDC_SIZE / 4], pdcseq_mem[GPU_PDC_SIZE / 4];
static int pdc_ro, rsc_stuck;
static uint32_t hw_ro_off; /* one GMU-block register that ignores writes */ /* PDC refuses writes / RSC never reports powered off */
static int wake_model, wake_seen, wake_ack_stuck, wake_busy_stuck, wake_stop_stuck;
static int retention_stuck, retention_restore_stuck, wake_gx_on;
static unsigned wake_trace_n;
static uint32_t wake_trace_off[16], wake_trace_val[16];
static int irq_model;
static unsigned irq_trace_n, irq_fail_write, irq_change;
static uint32_t irq_trace_off[8], irq_trace_value[8], irq_ao_readback, irq_hfi_readback;
static int smmu_sticky; /* hardware that refuses to take the ABL default back in S2CR3/CBAR3 */
static void test_store32(vm_offset_t base, uint32_t off, uint32_t value)
{
    all_mmio_writes++;
    if (hfi_fake_enabled && base == (vm_offset_t)fp6_gmu_regs && off == 0x47650u) {
        uint32_t *table = (uint32_t *)(void *)hfi_fake_mem;
        uint32_t *cmd_hdr = table + 6, *msg_hdr = table + 18;
        uint32_t *cmdq = table + FP6_GMU_HFI_QUEUE0 / 4;
        uint32_t *msgq = table + (FP6_GMU_HFI_QUEUE0 + 0x1000u) / 4;
        uint32_t request = cmdq[cmd_hdr[10]];
        cmd_hdr[10] = cmd_hdr[11]; /* GMU consumed the command. */
        unsigned wi = msg_hdr[11];
        /* Measured Gen8 TABLE ACKs retain ID 15 and use a 3-dword payload. */
        unsigned req_id = request & 0xffu;
        msgq[(wi + 0u) % 1024u] = (1u << 16) |
            ((req_id == 15u ? 3u : 4u) << 8) | (req_id == 15u ? req_id : 126u);
        msgq[(wi + 1u) % 1024u] = request;
        msgq[(wi + 2u) % 1024u] = hfi_fake_result;
        msgq[(wi + 3u) % 1024u] = 0; /* GMU_SUCCESS */
        msg_hdr[11] = (wi + 4u) % 1024u;
        fp6_gmu_regs[0x47648u / 4u] = 1u;
        return;
    }
    if (hfi_fake_enabled && base == (vm_offset_t)fp6_gmu_regs && off == 0x47644u) {
        fp6_gmu_regs[0x47648u / 4u] &= ~value;
        return;
    }
    if (fp6_gmu_clock_model && base == (vm_offset_t)fp6_gpucc) {
        if (off == 0x931c || off == 0x93f0)
            assert(!(fp6_gpucc[(off-4)/4] & (1u << 31))); /* root before CFG */
        if ((off == 0x9318 || off == 0x93ec) && (value & 2u) && !fp6_root_stuck)
            value &= ~((1u << 31) | 1u);
    }
    if (base == (vm_offset_t)fp6_rsc + 0xd00) {
        if (off == 8) { fp6_rsc[(0xd00+4)/4] &= ~value; return; }
        if (off == 0x24 && value == 0x1010000) {
            fp6_rsc[(0xd00+4)/4] |= 1;
            fp6_rsc[(0xd00+0x40)/4] = 0x10100;
            fp6_rsc[(0xd00+0x28)/4] = 1;
        }
    }
    if (base == (vm_offset_t)fp6_gpucc && fp6_power_mode) {
        /* gpucc CX GDSC: PWR_ON is reported in the hw-ctrl status register. */
        if (off == 0x9080) fp6_gpucc[0x9094/4] = (value & 1u) ? 0 : (1u << 31);
        if (off == 0x93ec && (value & 2u)) value &= ~((1u << 31) | 1u);
    }
    if ((base == (vm_offset_t)fp6_gpucc &&
        ((fp6_clock_refuse == 0 && off == 0x7000) || (fp6_clock_refuse == 3 && off == 0x90bc))) ||
        (base == (vm_offset_t)fp6_gcc_gpu &&
        ((fp6_clock_refuse == 1 && off == 0x10) || (fp6_clock_refuse == 2 && off == 0x18)))) return;
    if (irq_model && base == (vm_offset_t)gmu_mem && (off == 0x24c18 || off == 0x1464c)) {
        assert(irq_trace_n < 8);
        irq_trace_off[irq_trace_n] = off; irq_trace_value[irq_trace_n++] = value;
        if (irq_trace_n == irq_fail_write) return;
        if (irq_trace_n == 2) {
            if (irq_change == 1) gmu_mem[0x14648/4] = 1u << 15;
            if (irq_change == 2) gmu_mem[0x24c14/4] = 1;
            if (irq_change == 3) gmu_mem[0x14000/4] = 0;
            if (irq_change == 4) gmu_mem[0x14068/4] = 1;
            if (irq_change == 5) gmu_mem[0x14070/4] = 0xbabeface;
            if (irq_change == 6) gmu_mem[0x24c40/4] = 1;
            if (irq_change == 7) gmu_mem[0x143b0/4] = 0;
            if (irq_change == 8) cc[GPU_GX_GDSCR/4] |= GPU_DOMAIN_ON;
        }
        if (value == ~0u) value = off == 0x24c18 ? irq_ao_readback : irq_hfi_readback;
    }
    if (wake_model && base == (vm_offset_t)gmu_mem) {
        if (off == 0x14730 || off == 0x24c1c || off == 0x14000) {
            assert(wake_trace_n < 16);
            wake_trace_off[wake_trace_n] = off; wake_trace_val[wake_trace_n++] = value;
        }
        if (off == 0x14730 && ((value == 1 && retention_stuck) || (value == 0 && retention_restore_stuck))) return;
        if (off == 0x23034 || off == 0x2303c || off == 0x23044) return;
        if (off == 0x24c1c && (value == 1 || value == 2)) gmu_mem[0x23010/4] &= ~(1u << 16);
        if (off == 0x24c1c && value == 2) wake_seen = 1;
    }
    if (wake_model && base == (vm_offset_t)pdc_mem && (off == 0x55d4 || off == 0x55e4 || off == 0x55f4 ||
        off == 0x5764 || off == 0x5774 || off == 0x5784)) value &= ~8u;
    if (base == (vm_offset_t)smmu_mem) {
        smmu_write_calls++;
        if (off == GPU_SMMU_CB0 + 3 * 0x1000 + GPU_SMMU_CB_TLBSYNC)
            smmu_mem[(GPU_SMMU_CB0 + 3 * 0x1000 + GPU_SMMU_CB_TLBSTATUS)/4] = tlb_stuck ? 1 : 0;
        if (off == refuse_smmu_off && value && !refused_writes++) return;
    }
    if (base == (vm_offset_t)fp6_smmu && fp6_gpu_smmu_model) {
        if (off == 0x20010 && value == 0x00038011u) value |= 0x60u; /* measured TBI readback */
        if (off == 0x20000 && value == 0x1167u) value &= ~0x1000u; /* measured ASIDPNE readback */
    }
    if (base == (vm_offset_t)fp6_smmu && off == fp6_refuse_off &&
        fp6_refuse_nth && ++fp6_refuse_count == fp6_refuse_nth) return;
    if (base == (vm_offset_t)fp6_smmu && value == 0x00038011u) fp6_seen_tcr2 = value;
    if (base == (vm_offset_t)fp6_smmu && value == 0x0001f300u) fp6_seen_cbar = value;
    if (base == (vm_offset_t)fp6_smmu && (off & 0xfffu) == 0x58 && value == 0xffffffffu) {
        fp6_seen_fsr_clear = 1; value = 0; /* Context FSR is write-one-to-clear. */
    }
    /* A split ATS write is invalid even if the final bytes look correct. */
    if (base == (vm_offset_t)fp6_smmu)
        assert(off != FP6_TEST_CB_BASE + 0x800 && off != FP6_TEST_CB_BASE + 0x804);
    if (smmu_sticky && base == (vm_offset_t)smmu_mem &&
        ((off == GPU_SMMU_S2CR + 12 && value == GPU_SMMU_S2CR_FAULT) ||
         (off == GPU_SMMU_CBAR + 12 && value == 0))) return;
    if (hw_ro_off && base == (vm_offset_t)gmu_mem && off == hw_ro_off) return;
    if (pdc_ro && (base == (vm_offset_t)pdc_mem || base == (vm_offset_t)pdcseq_mem)) return;
    *(volatile uint32_t *)(base + off) = value;
}
static void test_store64(vm_offset_t base, uint32_t off, uint64_t value)
{
    all_mmio_writes++;
    if (base == (vm_offset_t)fp6_smmu) {
        if (fp6_gpu_smmu_model) {
            assert(off == 0x20020 || off == 0x20028);
        } else {
            assert(off == FP6_TEST_CB_BASE + 0x800 && value == 0x60000000ull);
            fp6_ats64_writes++;
            fp6_smmu[(FP6_TEST_CB_BASE + 0x8f0)/4] = 1;
        }
    }
    if (base == (vm_offset_t)smmu_mem) {
        smmu_write_calls++;
        if (off == refuse_smmu_off && value && !refused_writes++) return;
    }
    *(volatile uint64_t *)(base + off) = value;
}
static int smmu_maps, fail_smmu_map;
static int pdc_maps, seq_maps, fail_pdc_map, fail_seq_map;
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
    if (bad_atos == 1 && cur == 0x60006000u) par ^= 0x1000;
    if (bad_atos == 2 && cur == 0x6000d000u) par = fake_pa_base;
    smmu_mem[(cb + GPU_SMMU_CB_PAR) / 4] = (uint32_t)par;
    smmu_mem[(cb + GPU_SMMU_CB_PAR) / 4 + 1] = (uint32_t)(par >> 32);
}

static void fp6_smmu_sim(void)
{
    const unsigned cb = FP6_TEST_CB_BASE; /* Linux leaves CB0/1 to GPU; test SID5 on CB2 */
    uint64_t cur = fp6_smmu[ (cb + 0x800) / 4 ] |
        (uint64_t)fp6_smmu[(cb + 0x804) / 4] << 32;
    if (cur == fp6_last_ats) return;
    fp6_last_ats = cur;
    uint64_t par = 1;
    if ((fp6_smmu[cb / 4] & 1u) &&
        (fp6_smmu[(cb + 0x30) / 4] & 0x3f) == 32) {
        uint64_t table = fp6_smmu[(cb + 0x20) / 4] |
            (uint64_t)fp6_smmu[(cb + 0x24) / 4] << 32;
        uint64_t va = cur & 0xffffffffu;
        uint64_t e1 = dma_rd64(table + 8 * ((va >> 30) & 3));
        if ((e1 & 3) == 3) {
            uint64_t e2 = dma_rd64((e1 & 0xfffffffff000ull) + 8 * ((va >> 21) & 511));
            if ((e2 & 3) == 3) {
                uint64_t e3 = dma_rd64((e2 & 0xfffffffff000ull) + 8 * ((va >> 12) & 511));
                if ((e3 & 3) == 3 && (e3 & (1u << 10))) par = e3 & 0x0000fffffffff000ull;
            }
        }
    }
    fp6_smmu[(cb + 0x8f0) / 4] = 0;
    fp6_smmu[(cb + 0x50) / 4] = (uint32_t)par;
    fp6_smmu[(cb + 0x54) / 4] = (uint32_t)(par >> 32);
}

void clean_dcache64(addr64_t addr, unsigned count, int phys) {
    if (addr == (addr64_t)(uintptr_t)zap_region ||
        addr == (addr64_t)(uintptr_t)(zap_region + 0x1000)) {
        assert(count == 0x1000 && phys == 0);
        clean_calls++;
        return;
    }
    if (global_alloc_mode) {
        assert(addr >= (addr64_t)(uintptr_t)dma_block &&
            addr + count <= (addr64_t)(uintptr_t)(dma_block + sizeof(dma_block)) && phys == 0);
        clean_calls++; return;
    }
    assert(addr == fake_pa_base && phys == TRUE);
    clean_bytes = count; clean_calls++;
    if (count == GPU_BUF_BYTES) {
        assert(smmu_mem[(GPU_SMMU_CB0 + 3 * 0x1000) / 4] == 0);
        const uint32_t *h = (uint32_t *)(dma_block + GPU_BUF_HFI_OFF);
        const uint32_t expected[] = {0,120,6,12,2,2,
            1,0x6000a000,0xa00,1024,0,0,1,1,1,0,0,0,
            1,0x6000b000,0xa04,1024,0,0,1,1,1,0,0,0};
        assert(!memcmp(h, expected, sizeof(expected)));
        for (unsigned off = 0x3000; off < GPU_BUF_BYTES; off++)
            if (off < GPU_BUF_HFI_OFF || off >= GPU_BUF_HFI_OFF + sizeof(expected)) assert(dma_block[off] == 0);
    }
}
void flush_dcache64(addr64_t addr, unsigned count, int phys) {
    (void)addr; (void)count; (void)phys;
}
ppnum_t pmap_find_phys(pmap_t p, addr64_t va)
{
    (void)p;
    uint64_t offset = va - (addr64_t)(uintptr_t)dma_block;
    return (ppnum_t)((fake_pa_base + offset + (phys_discontig && offset >= 0x4000 ? 0x4000 : 0)) >> 14);
}
unsigned int pmap_cache_attributes(ppnum_t pn) { (void)pn; return VM_WIMG_DEFAULT; }
void pmap_set_cache_attributes(ppnum_t pn, unsigned int attr) { (void)pn; (void)attr; }
kern_return_t kmem_alloc_contig(vm_map_t m, vm_offset_t *a, vm_size_t size, vm_offset_t mask,
    unsigned x1, unsigned x2, unsigned flags, int tag)
{
    (void)m; (void)x1; (void)x2; (void)tag; (void)mask;
    alloc_calls++;
    assert(size <= sizeof(dma_block) && (flags & 2));
    if (fail_alloc) return 1;
    if (global_alloc_mode) {
        size_t bytes = (size + 0x3fffu) & ~0x3fffu;
        assert(global_alloc_offset + bytes <= sizeof(dma_block));
        *a = (vm_offset_t)dma_block + global_alloc_offset;
        memset((void *)(uintptr_t)*a, 0, bytes);
        global_alloc_offset += bytes;
        return KERN_SUCCESS;
    }
    memset(dma_block, 0, sizeof(dma_block));
    *a = alloc_null ? 0 : (vm_offset_t)dma_block + (alloc_unaligned ? 4 : 0);
    return KERN_SUCCESS;
}

void delay(int us)
{
    smmu_sim();
    fp6_smmu_sim();
    if (gmu_mem[0x24c1c / 4] == 1 && !rsc_stuck && !(wake_model && wake_seen && wake_stop_stuck)) {
        gmu_mem[(0x23000 + 4 * 4) / 4] |= 1u << 16;
        if (wake_model) {
            gmu_mem[0x23010/4] = 0x01010006;
            gmu_mem[0x24c20/4] = gmu_mem[0x23404/4] = 1;
            cc[GPU_GX_GDSCR/4] = GPU_CX_IDLE_GDSCR;
        }
    }
    if (wake_model && gmu_mem[0x24c1c/4] == 2 && !wake_ack_stuck) {
        gmu_mem[0x24c20/4] = 2;
        if (!wake_busy_stuck) gmu_mem[0x23404/4] = 0;
        if (wake_gx_on) cc[GPU_GX_GDSCR/4] |= GPU_DOMAIN_ON;
    }
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

int PE_current_console(PE_Video *video)
{
    memset(video, 0, sizeof(*video));
    return -1;
}

int PE_parse_boot_argn(const char *name, void *value, int length)
{
	if (strcmp(name, "fp6zap") == 0) {
		assert(length == sizeof(fp6_zap_mode));
		if (fp6_zap_mode != 0) memcpy(value, &fp6_zap_mode, sizeof(fp6_zap_mode));
		return fp6_zap_mode != 0;
	}
	if (strcmp(name, "fp6pas") == 0) {
		assert(length == sizeof(fp6_pas_mode));
		if (fp6_pas_mode != 0) memcpy(value, &fp6_pas_mode, sizeof(fp6_pas_mode));
		return fp6_pas_mode != 0;
	}
	if (strcmp(name, "fp6gpu") == 0) {
		assert(length == sizeof(fp6_mode));
		if (fp6_mode != 0) memcpy(value, &fp6_mode, sizeof(fp6_mode));
		return fp6_mode != 0;
	}
	if (strcmp(name, "fp6gmuload") == 0) { return 0; }
	if (strcmp(name, "fp6dpusnap") == 0) { return 0; }
	if (strcmp(name, "fp6gpuexec") == 0) { return 0; }
	if (strcmp(name, "fp6gmunopreempt") == 0) {
		assert(length == sizeof(fp6_gmu_no_preempt_mode));
		if (fp6_gmu_no_preempt_mode) memcpy(value, &fp6_gmu_no_preempt_mode, sizeof(fp6_gmu_no_preempt_mode));
		return fp6_gmu_no_preempt_mode != 0;
	}
	if (strcmp(name, "fp6smmupower") == 0) { memcpy(value, &fp6_power_mode, sizeof(fp6_power_mode)); return fp6_power_mode != 0; }
	if (strcmp(name, "fp6smmu") == 0) {
		assert(length == sizeof(fp6_smmu_mode));
		if (fp6_smmu_mode != 0) memcpy(value, &fp6_smmu_mode, sizeof(fp6_smmu_mode));
		return fp6_smmu_mode != 0;
	}
	if (strcmp(name, "fp6smmuirq") == 0) {
		assert(length == sizeof(fp6_smmu_irq_mode));
		if (fp6_smmu_irq_mode != 0) memcpy(value, &fp6_smmu_irq_mode, sizeof(fp6_smmu_irq_mode));
		return fp6_smmu_irq_mode != 0;
	}
    assert(strcmp(name, "sweetgpu") == 0 && length == sizeof(mode));
    if (present) memcpy(value, &mode, sizeof(mode));
    return present;
}

vm_offset_t ml_io_map(vm_offset_t physical, vm_size_t size)
{
    if (physical == 0x03d37000 && size == sizeof(fp6_gmu_regs)) return (vm_offset_t)fp6_gmu_regs;
    if (physical == 0x00100000 && size == sizeof(fp6_gcc_pll))
        return fp6_fail_pll_map ? 0 : (vm_offset_t)fp6_gcc_pll;
    if (physical == 0x00152000 && size == sizeof(fp6_gcc_votes)) return (vm_offset_t)fp6_gcc_votes;
    if (physical == 0x17100000 && size == sizeof(fp6_gicd)) {
        fp6_gicd_maps++;
        return fail_fp6_gicd_map ? 0 : (vm_offset_t)fp6_gicd;
    }
    if (physical == 0x03d90000 && size == sizeof(fp6_gpucc)) {
        fp6_map_calls++;
        return (vm_offset_t)fp6_gpucc;
    }
    if (physical == 0x03da0000 && size == sizeof(fp6_smmu)) {
        fp6_smmu_maps++;
        return (vm_offset_t)fp6_smmu;
    }
    if (physical == 0x00171000 && size == sizeof(fp6_gcc_gpu)) return (vm_offset_t)fp6_gcc_gpu;
    if (physical == 0x17a20000 && size == sizeof(fp6_rsc)) return (vm_offset_t)fp6_rsc;
    if (physical == 0x81c60000 && size == sizeof(fp6_cmd_db)) return (vm_offset_t)fp6_cmd_db;
    map_calls++;
    if (physical == GPU_GCC_PA && size == GPU_GCC_SIZE)
        return fail_gcc ? 0 : (vm_offset_t)gcc;
    if (physical == GPU_CC_PA && size == GPU_CC_SIZE)
        return fail_cc ? 0 : (vm_offset_t)cc;
    if (physical == GPU_PDC_PA && size == GPU_PDC_SIZE) {
        pdc_maps++;
        return fail_pdc_map ? 0 : (vm_offset_t)pdc_mem;
    }
    if (physical == GPU_PDC_SEQ_PA && size == GPU_PDC_SIZE) {
        seq_maps++;
        return fail_seq_map ? 0 : (vm_offset_t)pdcseq_mem;
    }
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

void fp6_scm_test_call(uint64_t fid, uint64_t arginfo, uint64_t arg0,
                       uint64_t *status, uint64_t *value)
{
    assert(scm_calls < 2);
    scm_fid[scm_calls] = fid;
    scm_arginfo[scm_calls] = arginfo;
    scm_arg0[scm_calls] = arg0;
    *status = scm_status[scm_calls];
    *value = scm_value[scm_calls];
    scm_calls++;
}

vm_offset_t ml_io_map_wcomb(vm_offset_t physical, vm_size_t size)
{
    assert(physical == 0x9ea9a000u && size == sizeof(zap_region));
    return zap_map_fail ? 0 : (vm_offset_t)zap_region;
}

void fp6_scm_test_call_full(uint64_t fid, uint64_t arginfo, uint64_t arg0,
                            uint64_t arg1, uint64_t arg2,
                            uint64_t *status, uint64_t *value)
{
    assert(scm_full_calls < 8);
    unsigned n = scm_full_calls++;
    scm_full[n].fid = fid; scm_full[n].arginfo = arginfo;
    scm_full[n].arg0 = arg0; scm_full[n].arg1 = arg1; scm_full[n].arg2 = arg2;
    *status = scm_full_fail_at == n + 1 ? 0xFFFFFFFFULL : 0;
    *value = 0;
    scm_full[n].status = *status; scm_full[n].value = *value;
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
    pdc_maps = seq_maps = fail_pdc_map = fail_seq_map = 0; pdc_ro = rsc_stuck = 0;
    for (unsigned i = 0; i < GPU_PDC_SIZE / 4; i++) { pdc_mem[i] = 0x9dc00000u | i; pdcseq_mem[i] = 0x5e900000u | i; }
    for (unsigned i = 0; i < GPU_SMMU_SIZE / 4; i++) smmu_mem[i] = 0x5e000000u | i;
    smmu_mem[0x20 / 4] = 5;    /* IDR0: NUMSMRG = 5 */
    smmu_mem[0x24 / 4] = 3;    /* IDR1: NUMCB = 3 */
    fake_pa_base = 0x90000000ull; fail_alloc = alloc_calls = clean_calls = 0;
    ats_stuck = tlb_stuck = smmu_sticky = 0;
    alloc_null = alloc_unaligned = phys_discontig = bad_atos = smmu_write_calls = 0;
    refuse_smmu_off = refused_writes = clean_bytes = 0; all_mmio_writes = 0;
    wake_model = wake_seen = wake_ack_stuck = wake_busy_stuck = wake_stop_stuck = 0;
    retention_stuck = retention_restore_stuck = wake_gx_on = 0; wake_trace_n = 0;
    irq_model = 0; irq_trace_n = irq_fail_write = irq_change = 0;
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

static void buffer_defaults(void)
{
    arc_reset(); mode = 11;
    cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR;
    memset(gmu_mem, 0, sizeof(gmu_mem)); gmu_mem[0x14000/4] = 1;
    memset(pdc_mem, 0, sizeof(pdc_mem)); memset(pdcseq_mem, 0, sizeof(pdcseq_mem));
    memset(smmu_mem, 0, sizeof(smmu_mem));
    smmu_mem[0] = 0x00200626; smmu_mem[0x20/4] = 0x48016605;
    smmu_mem[0x24/4] = 0x20008005; smmu_mem[0x28/4] = 0x7511;
    for (unsigned i = 0; i < 5; i++) smmu_mem[GPU_SMMU_S2CR/4+i] = GPU_SMMU_S2CR_FAULT;
    last_ats = 0;
    struct gpu_power_experiment *x = &gpu_boot_inventory.power;
    gpu_smmu_read(x);
    x->fw_checked = x->fw_written = 8192; x->fw_size = 32768;
}

static void wake_defaults(void)
{
    buffer_defaults(); mode = 13; wake_model = 1; cc[GPU_GX_GDSCR/4] = GPU_CX_IDLE_GDSCR;
    struct gpu_power_experiment *x = &gpu_boot_inventory.power;
    x->preboot_requested = 1; x->preboot_done = 29;
    x->buf.requested = x->buf.inactive = 1; x->buf.stage = 3;
    x->buf.checks = x->buf.passed = 29;
    x->init_requested = x->init_done_writes = x->init_stop_done = 1;
    x->init_nwrites = 48; x->init_bad = x->init_nbad_log = 9;
    const uint32_t off[] = {0x23034,0x2303c,0x23044,0x55d4,0x55e4,0x55f4,0x5764,0x5774,0x5784};
    for (unsigned i = 0; i < 9; i++) {
        x->init_bad_off[i] = off[i]; x->init_bad_region[i] = i < 3 ? 0 : 1;
        x->init_bad_wrote[i] = i < 3 ? 0 : 0x10108;
        x->init_bad_got[i] = i == 0 ? 0x82204514u : i == 1 ? 0x82204510u : i == 2 ? 0x82204520u : 0x10100;
        if (i < 3) gmu_mem[off[i]/4] = x->init_bad_got[i];
    }
    gmu_mem[0x14730/4] = gmu_mem[0x24c1c/4] = 0;
    gmu_mem[0x24c20/4] = gmu_mem[0x23404/4] = 1;
    gmu_mem[0x23010/4] = 0x01010006;
}

static void irq_defaults(void)
{
    wake_defaults(); mode = 15; irq_model = 1; irq_ao_readback = 0x3f; irq_hfi_readback = ~0u;
    struct gpu_power_experiment *x = &gpu_boot_inventory.power;
    x->irq_preflight_requested = 1; x->irq_preflight_done = 6;
    /* Independent constants from 0096, not the implementation's expected array. */
    const unsigned off[] = {0x24c18,0x1464c,0x14648,0x24c14,0x24c40,0x143b0};
    for (unsigned i = 0; i < 6; i++) x->irq_preflight_value[i] = gmu_mem[off[i]/4] = i == 5 ? 15u : 0u;
}

int main(void)
{
    /* PM4 type-7 parity and the opt-in refusal path are independent checks. */
    assert(fp6_cp_type7_packet(0x17u, 1u) == 0x70970001u);
    assert(fp6_cp_type7_packet(0x48u, 7u) == 0x70c80007u);
    assert(fp6_cp_type7_packet(0x3du, 3u) == 0x703d8003u);
    int writes_before_exec_skip = all_mmio_writes;
    output[0] = 0;
    assert(fp6_gpu_exec_probe(0, 0, NULL, NULL));
    assert(all_mmio_writes == writes_before_exec_skip);
    assert(strstr(output, "skipped; fp6gpuexec=1 not requested"));

    /* Gen8 HFI v5 GET_VALUE returns data in ACK[2], status in ACK[3]. */
    uint32_t hfi_result = 0xffffffffu;
    uint32_t hfi_ack_v5[] = {0, 0, 1, 0};
    assert(fp6_gmu_hfi_ack_status_result(hfi_ack_v5, 4, &hfi_result) && hfi_result == 1);
    hfi_ack_v5[3] = 4; hfi_result = 0xffffffffu;
    assert(!fp6_gmu_hfi_ack_status_result(hfi_ack_v5, 4, &hfi_result) && hfi_result == 1);
    uint32_t hfi_ack_legacy[] = {0, 0, 0}; hfi_result = 0xffffffffu;
    assert(fp6_gmu_hfi_ack_status_result(hfi_ack_legacy, 3, &hfi_result) && hfi_result == 0);
    hfi_ack_legacy[2] = 1;
    assert(!fp6_gmu_hfi_ack_status_result(hfi_ack_legacy, 3, &hfi_result));
    assert(!fp6_gmu_hfi_ack_status_result(hfi_ack_legacy, 2, &hfi_result));

    /* The opt-in no-preemption probe sends no feature request; default still sends Linux's A810 level-1 request. */
    static uint8_t preempt_queue_mem[FP6_GMU_HFI_SIZE];
    memset(preempt_queue_mem, 0, sizeof(preempt_queue_mem));
    uint32_t *preempt_table = (uint32_t *)(void *)preempt_queue_mem;
    uint32_t *preempt_cmd_hdr = preempt_table + 6, *preempt_msg_hdr = preempt_table + 18;
    preempt_cmd_hdr[0] = preempt_msg_hdr[0] = 1u;
    preempt_cmd_hdr[1] = fp6_gmu_hfi_va + FP6_GMU_HFI_QUEUE0;
    preempt_msg_hdr[1] = fp6_gmu_hfi_va + FP6_GMU_HFI_QUEUE0 + 0x1000u;
    preempt_cmd_hdr[3] = preempt_msg_hdr[3] = 1024u;
    hfi_fake_mem = preempt_queue_mem; hfi_fake_result = 0; hfi_fake_enabled = 1;
    unsigned preempt_sequence = 0;
    fp6_gmu_no_preempt_mode = 1; output[0] = 0;
    assert(fp6_gmu_hfi_configure_preemption((vm_offset_t)fp6_smmu, 0x20000u,
        (vm_offset_t)fp6_gmu_regs, preempt_queue_mem, &preempt_sequence));
    assert(preempt_sequence == 0 && preempt_cmd_hdr[11] == 0);
    assert(strstr(output, "HFI preemption disabled by fp6gmunopreempt probe"));
    fp6_gmu_no_preempt_mode = 0; output[0] = 0;
    assert(fp6_gmu_hfi_configure_preemption((vm_offset_t)fp6_smmu, 0x20000u,
        (vm_offset_t)fp6_gmu_regs, preempt_queue_mem, &preempt_sequence));
    assert(preempt_sequence == 1 && preempt_cmd_hdr[11] == 4);
    uint32_t *preempt_cmdq = preempt_table + FP6_GMU_HFI_QUEUE0 / 4;
    assert((preempt_cmdq[0] & 0xffu) == 11u && preempt_cmdq[1] == 2u &&
        preempt_cmdq[2] == 1u && preempt_cmdq[3] == 0xdu);
    hfi_fake_enabled = 0;
    puts("PASS: opt-in HFI no-preemption omits only the feature command; default A810 request remains intact");

    /* Exercise queue ownership/ACK parsing for GET_VALUE and Gen8's one-dword START. */
    static uint8_t hfi_queue_mem[FP6_GMU_HFI_SIZE];
    memset(hfi_queue_mem, 0, sizeof(hfi_queue_mem));
    uint32_t *hfi_table = (uint32_t *)(void *)hfi_queue_mem;
    uint32_t *hfi_cmd_hdr = hfi_table + 6, *hfi_msg_hdr = hfi_table + 18;
    hfi_cmd_hdr[0] = hfi_msg_hdr[0] = 1u;
    hfi_cmd_hdr[1] = fp6_gmu_hfi_va + FP6_GMU_HFI_QUEUE0;
    hfi_msg_hdr[1] = fp6_gmu_hfi_va + FP6_GMU_HFI_QUEUE0 + 0x1000u;
    hfi_cmd_hdr[3] = hfi_msg_hdr[3] = 1024u;
    hfi_fake_mem = hfi_queue_mem; hfi_fake_result = 1; hfi_fake_enabled = 1;
    unsigned hfi_sequence = 0; uint32_t hfi_value = 0;
    uint32_t get_context_queue[3] = { fp6_hfi_hdr(12u, 3u), 121u, 0u };
    assert(fp6_gmu_hfi_send_req((vm_offset_t)fp6_smmu, 0x20000u,
        (vm_offset_t)fp6_gmu_regs, hfi_queue_mem, get_context_queue, 3u,
        &hfi_sequence, &hfi_value));
    assert(hfi_value == 1u && hfi_sequence == 1u);
    uint32_t gpu_start[1] = { fp6_hfi_hdr(10u, 1u) };
    assert(fp6_gmu_hfi_send_req((vm_offset_t)fp6_smmu, 0x20000u,
        (vm_offset_t)fp6_gmu_regs, hfi_queue_mem, gpu_start, 1u,
        &hfi_sequence, NULL));
    assert(hfi_sequence == 2u);
    hfi_fake_enabled = 0;
    puts("PASS: HFI GET_VALUE and one-dword START share the bounded queue dispatcher");

    /* Linux's post-START FP6 defaults are separate GPU and bus votes. */
    static uint8_t hfi_vote_mem[FP6_GMU_HFI_SIZE];
    memset(hfi_vote_mem, 0, sizeof(hfi_vote_mem));
    uint32_t *vote_table = (uint32_t *)(void *)hfi_vote_mem;
    uint32_t *vote_cmd_hdr = vote_table + 6, *vote_msg_hdr = vote_table + 18;
    vote_cmd_hdr[0] = vote_msg_hdr[0] = 1u;
    vote_cmd_hdr[1] = fp6_gmu_hfi_va + FP6_GMU_HFI_QUEUE0;
    vote_msg_hdr[1] = fp6_gmu_hfi_va + FP6_GMU_HFI_QUEUE0 + 0x1000u;
    vote_cmd_hdr[3] = vote_msg_hdr[3] = 1024u;
    hfi_fake_mem = hfi_vote_mem; hfi_fake_result = 0; hfi_fake_enabled = 1;
    unsigned vote_sequence = 0;
    assert(fp6_gmu_hfi_default_votes((vm_offset_t)fp6_smmu, 0x20000u,
        (vm_offset_t)fp6_gmu_regs, hfi_vote_mem, &vote_sequence));
    uint32_t *vote_cmdq = vote_table + FP6_GMU_HFI_QUEUE0 / 4;
    assert(vote_sequence == 2u && vote_cmd_hdr[10] == vote_cmd_hdr[11]);
    assert((vote_cmdq[0] & 0xffu) == 30u && ((vote_cmdq[0] >> 8) & 0xffu) == 4u &&
        vote_cmdq[1] == 1u && vote_cmdq[2] == 2u && vote_cmdq[3] == 0xffff00ffu);
    assert((vote_cmdq[4] & 0xffu) == 30u && ((vote_cmdq[4] >> 8) & 0xffu) == 4u &&
        vote_cmdq[5] == 1u && vote_cmdq[6] == 0xffu && vote_cmdq[7] == 0xffff0002u);
    assert(vote_msg_hdr[10] == vote_msg_hdr[11]);
    hfi_fake_enabled = 0;
    puts("PASS: FP6 HFI default GPU pwrlevel-8 and bus-level-2 votes are ACKed before OOB");

    /* Match the measured SMMU IDs and its TBI/ASIDPNE readback quirks while
     * enabling the isolated GPU TTBR1 context. The refused preflight must not write. */
    memset(fp6_smmu, 0, sizeof(fp6_smmu));
    fp6_smmu[0x20/4] = 0x4c017e18u; fp6_smmu[0x24/4] = 0x40000016u;
    fp6_smmu[0x28/4] = 0x5511u; fp6_smmu[0] = 0x00200626u;
    for (unsigned i = 0; i < 24; i++) fp6_smmu[(0xc00 + 4*i)/4] = 0x20000u;
    fp6_gpu_global_domain.l0.va = dma_block; fp6_gpu_global_domain.l0.pa = 0x900000000ULL;
    fp6_smmu[0x1000/4] = 1; all_mmio_writes = 0;
    output[0] = 0;
    assert(!fp6_gpu_global_context_enable((vm_offset_t)fp6_smmu) && all_mmio_writes == 0);
    assert(strstr(output, "CB0 takeover refused group=0/24"));
    assert(strstr(output, "CBAR=0x00000001"));
    fp6_smmu[0x1000/4] = 0;

    /* A live stream routed to CB0 must prevent takeover even when it is not SID0. */
    fp6_smmu[0x808/4] = 0x80000007u; fp6_smmu[0xc08/4] = 0u;
    all_mmio_writes = 0; output[0] = 0;
    assert(!fp6_gpu_global_context_enable((vm_offset_t)fp6_smmu) && all_mmio_writes == 0);
    assert(strstr(output, "CB0 already routed by group=2 SID=0x7"));
    fp6_smmu[0x808/4] = 0; fp6_smmu[0xc08/4] = 0x20000u;

    /* A powered CB0 with translation enabled is still never overwritten. */
    fp6_smmu[0x20000/4] = 0x2ff54315u;
    all_mmio_writes = 0; output[0] = 0;
    assert(!fp6_gpu_global_context_enable((vm_offset_t)fp6_smmu) && all_mmio_writes == 0);
    assert(strstr(output, "SCTLR=0x2ff54315"));

    /* The phone's measured stale TTBR/TCR/MAIR image is replaceable only
     * because CBAR/CBA2R are zero, SCTLR.M is clear, FSR is clear and routes
     * to CB0 are absent. Model the CB2 SID5 route and SID0's free group. */
    fp6_smmu[0x20000/4] = 0x2ff54314u;
    fp6_smmu[0x20030/4] = 0x710e6fccu;
    fp6_smmu[0x20010/4] = 0x00030065u;
    fp6_smmu[0x20020/4] = 0x0fc36d7bu; fp6_smmu[0x20024/4] = 0x19b3d377u;
    fp6_smmu[0x20028/4] = 0xaf8db9f4u; fp6_smmu[0x2002c/4] = 0xdc20c4a9u;
    fp6_smmu[0x20038/4] = 0x069faeaau; fp6_smmu[0x2003c/4] = 0x8c99bf1fu;
    fp6_smmu[0x800/4] = 0x80000005u; fp6_smmu[0xc00/4] = 2u;
    fp6_gpu_smmu_model = 1; all_mmio_writes = 0; output[0] = 0;
    assert(fp6_gpu_global_context_enable((vm_offset_t)fp6_smmu));
    assert(strstr(output, "replacing stale disabled CB0"));
    assert(fp6_smmu[0x20000/4] == 0x167u);
    assert(fp6_smmu[0x20010/4] == 0x38071u);
    assert(((uint64_t)fp6_smmu[0x20028/4] | ((uint64_t)fp6_smmu[0x2002c/4] << 32)) == 0x900000000ULL);
    assert(fp6_smmu[0xc00/4] == 2u && fp6_smmu[0x800/4] == 0x80000005u);
    assert(fp6_smmu[0xc04/4] == 0u && fp6_smmu[0x804/4] == 0x80000000u);
    int context_writes = all_mmio_writes;
    assert(fp6_gpu_global_context_enable((vm_offset_t)fp6_smmu) && all_mmio_writes == context_writes);
    fp6_gpu_smmu_model = 0; fp6_gpu_global_domain = (struct fp6_gpu_global_domain){0};
    fp6_gpu_smmu_base = 0; fp6_gpu_smmu_live = 0;
    puts("PASS: GPU SID0 TTBR1 setup replaces only stale disabled CB0, protects live routes, and accepts measured TBI/ASIDPNE readbacks");

    /* Run the actual GFX_ACC MEM_ALLOC path with distinct contiguous host pages,
     * then verify the HFI ACK VA, published leaf and live TTBR1 route. */
    memset(fp6_smmu, 0, sizeof(fp6_smmu));
    fp6_smmu[0x20/4] = 0x4c017e18u; fp6_smmu[0x24/4] = 0x40000016u;
    fp6_smmu[0x28/4] = 0x5511u; fp6_smmu[0] = 0x00200626u;
    for (unsigned i = 0; i < 24; i++) fp6_smmu[(0xc00 + 4*i)/4] = 0x20000u;
    fp6_gpu_global_domain = (struct fp6_gpu_global_domain){0};
    fp6_gpu_smmu_base = 0; fp6_gpu_smmu_live = 0; fp6_hfi_mem_alloc_count = 0;
    global_alloc_mode = 1; global_alloc_offset = 0; fake_pa_base = 0x900000000ULL;
    fp6_gpu_smmu_model = 1; fp6_gmu_hfi_va = 0x60000000u;
    static uint8_t hfi_mem[FP6_GMU_HFI_SIZE]; memset(hfi_mem, 0, sizeof(hfi_mem));
    uint32_t *queue = (uint32_t *)(void *)(hfi_mem + 24);
    queue[0] = 1; queue[1] = fp6_gmu_hfi_va + FP6_GMU_HFI_QUEUE0; queue[3] = 1024;
    uint32_t request[11] = {0x1234u,0, 0,0,FP6_HFI_MEMFLAG_GFX_ACC,2,0,0xabcdu,0,0x3000,12};
    unsigned sequence = 0; all_mmio_writes = 0;
    assert(fp6_gmu_hfi_mem_alloc((vm_offset_t)fp6_smmu, 0x20000,
        (vm_offset_t)fp6_gmu_regs, hfi_mem, request, 1, &sequence));
    assert(sequence == 1 && fp6_hfi_mem_alloc_count == 1 && fp6_gpu_smmu_live);
    assert(fp6_gpu_global_walk(&fp6_gpu_global_domain, FP6_GPU_GLOBAL_BASE) ==
        fp6_hfi_mem_allocs[0].backing.pa);
    uint32_t *reply = (uint32_t *)(void *)(hfi_mem + FP6_GMU_HFI_QUEUE0);
    assert(reply[0] == ((1u << 20) | (1u << 16) | (11u << 8) | 0x14u) && reply[1] == request[0]);
    assert(reply[2] == (uint32_t)FP6_GPU_GLOBAL_BASE && reply[3] == (uint32_t)(FP6_GPU_GLOBAL_BASE >> 32));
    assert(reply[6] == 0xabcdu && reply[8] == 0 && reply[9] == 0x3000);
    assert(fp6_smmu_read32((vm_offset_t)fp6_smmu, 0x20000) == 0x167u);
    global_alloc_mode = fp6_gpu_smmu_model = 0;
    puts("PASS: HFI GFX_ACC allocation returns a live GPU TTBR1 mapping and matching ACK");
    reset(); present = 0; sweet_gpu_probe();
    assert(map_calls == 0 && output[0] == 0);
    reset(); mode = 0; sweet_gpu_probe(); assert(map_calls == 0);
    reset(); mode = 16; sweet_gpu_probe(); assert(map_calls == 0);
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
        assert(x->ctx_nlog >= 18 && x->ctx_log_off[0] == GPU_SMMU_CBA2R + 12);
        for (unsigned i = 0; i < x->ctx_nlog; i++) assert(x->ctx_log_wrote[i] == x->ctx_log_got[i]);
        /* Hardware that keeps S2CR3/CBAR3: alternatives tried, mismatches reported. */
        arc_reset(); mode = 8; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        SMMU_DEFAULTS(); smmu_sticky = 1;
        arc_run(); x = &gpu_boot_inventory.power;
        assert(!x->ctx_error && x->ctx_passed == 4 && !x->ctx_restored);
        assert(x->ctx_final[0] == 0 && x->ctx_final[1] == 0x00020000u && x->ctx_final[2] == 0 &&
               x->ctx_final[3] == (2u << 16));
        assert(strstr(output, "MISMATCH") && strstr(output, "did not restore to the ABL default"));
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
    /* sweetgpu=9: RSC/PDC read-only inventory. */
    {
        uint32_t gb[GPU_GMU_SIZE / 4], pb[GPU_PDC_SIZE / 4], sb[GPU_PDC_SIZE / 4];
        arc_reset(); mode = 9; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        memcpy(pb, pdc_mem, sizeof(pb)); memcpy(sb, pdcseq_mem, sizeof(sb));
        arc_run(); x = &gpu_boot_inventory.power;
        assert(x->rsc_requested && x->rsc_done == GPU_RSC_READS && x->pdc_done == GPU_PDC_READS &&
               x->seq_done == GPU_PDC_SEQ_READS && pdc_maps == 1 && seq_maps == 1);
        assert(!memcmp(pb, pdc_mem, sizeof(pb)) && !memcmp(sb, pdcseq_mem, sizeof(sb))); /* no writes */
        /* Offsets: mainline dword indexes x4 from gmu+0x23000; handshake regs in the GMU block. */
        assert(gpu_rsc_regs[8].off == 0x23000 + 0x101 * 4 && gpu_rsc_regs[12].off == 0x24c1c &&
               gpu_rsc_regs[13].off == 0x24c20);
        assert(x->rsc_value[8] == gmu_mem[(0x23000 + 0x101 * 4) / 4]);
        assert(x->pdc_value[0] == pdc_mem[0x4500 / 4] && x->pdc_value[1] == pdc_mem[0x4520 / 4]);
        assert(x->seq_value[3] == pdcseq_mem[3]);
        assert(strstr(output, "RSC SEQ_BUSY_DRV0 +0x23404") && strstr(output, "PDC GPU_ENABLE_PDC +0x4500"));
        output[0] = 0; sweet_gpu_replay(); assert(pdc_maps == 1 && strstr(output, "PDC SEQ_MEM_4"));
        /* Mapping failures are reported, not fatal. */
        arc_reset(); mode = 9; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        fail_pdc_map = 1; arc_run(); x = &gpu_boot_inventory.power;
        assert(x->rsc_done == GPU_RSC_READS && !x->pdc_mapped && x->seq_done == GPU_PDC_SEQ_READS);
        assert(strstr(output, "(not mapped)"));
        arc_reset(); mode = 9; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        fail_seq_map = 1; arc_run(); assert(!gpu_boot_inventory.power.seq_mapped && gpu_boot_inventory.power.pdc_done == GPU_PDC_READS);
        /* Modes below 9 never map the PDC; no GMU access unless clocks came up. */
        arc_reset(); mode = 8; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1;
        arc_run(); assert(pdc_maps == 0 && seq_maps == 0 && !gpu_boot_inventory.power.rsc_requested);
        arc_reset(); mode = 9; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; gmu_mem[0x14000 / 4] = 1; clk_stuck = 2;
        memcpy(gb, gmu_mem, sizeof(gb)); arc_run();
        assert(pdc_maps == 0 && gmu_maps == 0 && !gpu_boot_inventory.power.rsc_requested);
    }
    /* sweetgpu=10: mainline rpmh_init writes with readback + RSC stop handshake. */
    {
#define RPMH_DEFAULTS() do { gmu_mem[0x14000 / 4] = 1; gmu_mem[0x24c1c / 4] = 0; \
        gmu_mem[(0x23000 + 0x101 * 4) / 4] = 0; gmu_mem[(0x23000 + 0x180 * 4) / 4] = 0; \
        gmu_mem[(0x23000 + 4 * 4) / 4] = 0; pdc_mem[0x4500 / 4] = 0; pdcseq_mem[0] = 0; } while (0)
        uint32_t gb[GPU_GMU_SIZE / 4], pb[GPU_PDC_SIZE / 4], sb[GPU_PDC_SIZE / 4];
        arc_reset(); mode = 10; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; RPMH_DEFAULTS();
        arc_run(); x = &gpu_boot_inventory.power;
        assert(x->init_requested && !x->init_error && x->init_nwrites == GPU_RPMH_INIT_COUNT &&
               x->init_bad == 0 && x->init_stop_done && x->init_done_writes);
        assert(GPU_RPMH_INIT_COUNT == 17 + 5 + 24 + 2 - 3 + 0 || GPU_RPMH_INIT_COUNT > 40);
        assert(pdc_mem[0x4500 / 4] == 0x80000001u && pdc_mem[0x4520 / 4] == 0);
        assert(pdc_mem[0x15d7 * 4 / 4] == 7 && pdc_mem[0x15e3] == 3 && pdc_mem[0x15df] == 2 && pdc_mem[0x157e] == 0x30090);
        assert(pdc_mem[0x1576] == 0x30010 && pdc_mem[0x157a] == 0x30000 && pdc_mem[0x1573] == 7);
        assert(pdcseq_mem[0] == 0xfebea1e1u && pdcseq_mem[4] == 0x002081fcu);
        assert(gmu_mem[(0x23000 + 0x180 * 4) / 4] == 0xa7a506a0u && gmu_mem[(0x23000 + 0x184 * 4) / 4] == 0x0020e8a8u);
        assert(gmu_mem[(0x23000 + 8 * 4) / 4] == 0x4520 && gmu_mem[(0x23000 + 0x12 * 4) / 4] == 0x80000000u);
        assert(gmu_mem[0x24c1c / 4] == 0); /* request dropped again */
        assert(strstr(output, "RPMH init result: all writes read back"));
        output[0] = 0; sweet_gpu_replay(); assert(strstr(output, "RPMH init writes=") && pdc_maps == 1);
        /* Unexpected pre-state: nothing written anywhere. */
        for (unsigned bad = 0; bad < 5; bad++) {
            arc_reset(); mode = 10; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; RPMH_DEFAULTS();
            if (bad == 0) pdc_mem[0x4500 / 4] = 1;
            if (bad == 1) pdcseq_mem[0] = 5;
            if (bad == 2) gmu_mem[(0x23000 + 0x180 * 4) / 4] = 9;
            if (bad == 3) gmu_mem[0x24c1c / 4] = 2;
            if (bad == 4) gmu_mem[(0x23000 + 0x101 * 4) / 4] = 1;
            memcpy(gb, gmu_mem, sizeof(gb)); memcpy(pb, pdc_mem, sizeof(pb)); memcpy(sb, pdcseq_mem, sizeof(sb));
            arc_run(); x = &gpu_boot_inventory.power;
            assert(x->init_requested && x->init_error && x->init_nwrites == 0);
            /* TCM (below 0xb000, firmware step) legitimately changes; the RSC/PDC area must not. */
            assert(!memcmp(gb + 0x23000 / 4, gmu_mem + 0x23000 / 4, sizeof(gb) - 0x23000) &&
                   !memcmp(pb, pdc_mem, sizeof(pb)) && !memcmp(sb, pdcseq_mem, sizeof(sb)));
        }
        /* PDC refuses writes: counted, handshake still attempted and reported. */
        arc_reset(); mode = 10; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; RPMH_DEFAULTS(); pdc_ro = 1;
        arc_run(); x = &gpu_boot_inventory.power;
        assert(x->init_bad > 20 && x->init_nwrites == GPU_RPMH_INIT_COUNT && x->init_first_bad_region == 2 &&
               x->init_error && strstr(output, "RPMH init first bad region="));
        assert(x->init_nbad_log == 16 && x->init_bad_region[0] == 2 && x->init_bad_off[0] == 0 &&
               x->init_bad_wrote[0] == 0xfebea1e1u && x->init_bad_got[0] == pdcseq_mem[0] &&
               strstr(output, "RPMH init bad region=2 off=+0x0 wrote=0xfebea1e1"));
        /* Pre-write table state is reported entry by entry and counts differences. */
        assert(x->tbl_done == GPU_RPMH_INIT_COUNT && strstr(output, "RPMH table pre-write:") &&
               strstr(output, "RPMH table pre-write region="));
        /* A single register that cannot be written is the only bad entry. */
        arc_reset(); mode = 10; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; RPMH_DEFAULTS();
        gmu_mem[(0x23000 + 0x0d * 4) / 4] = 0x82204514u; hw_ro_off = 0x23000 + 0x0d * 4;
        arc_run(); x = &gpu_boot_inventory.power;
        assert(x->init_bad == 1 && x->init_nbad_log == 1 && x->init_bad_off[0] == 0x23034 &&
               x->init_bad_got[0] == 0x82204514u && x->init_stop_done);
        hw_ro_off = 0;
        /* Table already programmed (persisted from an earlier boot): reported, not rewritten. */
        arc_reset(); mode = 10; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; RPMH_DEFAULTS();
        for (unsigned i = 0; i < GPU_RPMH_INIT_COUNT; i++) {
            uint32_t *w = gpu_rpmh_init[i].region == 0 ? &gmu_mem[gpu_rpmh_init[i].off / 4] :
                gpu_rpmh_init[i].region == 1 ? &pdc_mem[gpu_rpmh_init[i].off / 4] : &pdcseq_mem[gpu_rpmh_init[i].off / 4];
            *w = gpu_rpmh_init[i].value;
        }
        gmu_mem[0x24c1c / 4] = 0;
        arc_run(); x = &gpu_boot_inventory.power;
        assert(x->init_error && x->init_nwrites == 0 && strstr(output, "0 of 48 entries differ"));
        /* RSC never reports powered off: bounded, request dropped. */
        arc_reset(); mode = 10; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; RPMH_DEFAULTS(); rsc_stuck = 1;
        arc_run(); x = &gpu_boot_inventory.power;
        assert(!x->init_stop_done && x->init_error && gmu_mem[0x24c1c / 4] == 0);
        /* Mode 9 never writes the PDC/RSC. */
        arc_reset(); mode = 9; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; RPMH_DEFAULTS();
        memcpy(pb, pdc_mem, sizeof(pb)); arc_run();
        assert(!gpu_boot_inventory.power.init_requested && !memcmp(pb, pdc_mem, sizeof(pb)));
    }
    /* 0093: full memory layout, every refusal before SMMU writes, and rollback. */
    {
        const unsigned cb = GPU_SMMU_CB0 + 3 * 0x1000;
        struct gpu_buffer_probe *b;
        struct gpu_power_experiment *x;
        uint32_t before[GPU_SMMU_SIZE / 4], gb[GPU_GMU_SIZE / 4];
        buffer_defaults(); x = &gpu_boot_inventory.power;
        gpu_gmu_buffers((vm_offset_t)gmu_mem, (vm_offset_t)smmu_mem, x); b = &x->buf;
        assert(!b->error && b->stage == 3 && b->passed == 29 && b->checks == 29 && b->inactive && b->restored);
        assert(clean_calls == 1 && clean_bytes == 0x10000 && alloc_calls == 1);
        assert(b->va[0] == 0x60000000 && b->va[25] == 0x6000cfff && b->va[26] == 0x5ffff000 &&
               b->va[27] == 0x6000d000 && b->va[28] == 0x20000000);
        assert(b->nwrites == 20 && b->wrote[4] == fake_pa_base && b->got[9] == 0x80000005u);
        for (unsigned i = 0; i < 13; i++)
            assert(*(uint64_t *)(dma_block + 0x2000 + 8*i) == ((fake_pa_base+0x3000+0x1000*i) | GPU_PTE_PAGE));
        assert(*(uint64_t *)(dma_block + 0x2000 + 13*8) == 0);
        /* One independent mutation for every term of the precondition. */
        for (unsigned bad = 0; bad < 33; bad++) {
            buffer_defaults(); x = &gpu_boot_inventory.power;
            switch (bad) {
            case 0: gmu_mem[0x14000/4] = 0; break;
            case 1: gmu_mem[0x14068/4] = 1; break;
            case 2: x->fw_checked--; break;
            case 3: x->fw_written--; break;
            case 4: x->fw_size--; break;
            case 5: x->fw_bad = 1; break;
            case 6: x->fw_error = "firmware test failure"; break;
            case 7: x->smmu_gr0_done--; break;
            case 8: x->smmu_gr0[0] ^= 1; break;
            case 9: x->smmu_gr0[4] ^= 1; break;
            case 10: x->smmu_gr0[5] ^= 1; break;
            case 11: x->smmu_gr0[6] ^= 1; break;
            case 12: x->smmu_nsmr = 4; break;
            case 13: x->smmu_ncb = 3; break;
            case 14: smmu_mem[(GPU_SMMU_SMR+12)/4] = 5; break;
            case 15: smmu_mem[GPU_SMMU_SMR/4] = 0x80000005; break;
            case 16: smmu_mem[(GPU_SMMU_SMR+4)/4] = 0x80000009; break;
            case 17: smmu_mem[(GPU_SMMU_S2CR+12)/4] = 4; break;
            case 18: smmu_mem[(GPU_SMMU_CBAR+12)/4] = 0x20000; break;
            case 19: smmu_mem[(GPU_SMMU_CBA2R+12)/4] = 1; break;
            case 20: smmu_mem[(cb+GPU_SMMU_CB_TTBR0)/4] = 1; break;
            case 21: smmu_mem[cb/4] = 1; break;
            case 22: smmu_mem[(cb+GPU_SMMU_CB_TCR2)/4] = 1; break;
            case 23: smmu_mem[(cb+GPU_SMMU_CB_TCR)/4] = 1; break;
            case 24: smmu_mem[(cb+GPU_SMMU_CB_MAIR0)/4] = 1; break;
            case 25: smmu_mem[(cb+GPU_SMMU_CB_MAIR1)/4] = 1; break;
            case 26: fail_alloc = 1; break;
            case 27: alloc_null = 1; break;
            case 28: alloc_unaligned = 1; break;
            case 29: fake_pa_base = 0; break;
            case 30: fake_pa_base = 1ull << 36; break;
            case 31: fake_pa_base = (1ull << 36) - 0x4000; break;
            case 32: phys_discontig = 1; break;
            }
            memcpy(before, smmu_mem, sizeof(before)); memcpy(gb, gmu_mem, sizeof(gb));
            gpu_gmu_buffers((vm_offset_t)gmu_mem, (vm_offset_t)smmu_mem, x); b = &x->buf;
            assert(b->requested && b->error && b->stage == 0 && b->nwrites == 0 && smmu_write_calls == 0);
            assert(!memcmp(before, smmu_mem, sizeof(before)) && !memcmp(gb, gmu_mem, sizeof(gb)));
            assert(!clean_calls && !b->checks);
        }
        /* Every group must be inactive, including invalid nonzero SMRs. */
        for (unsigned i = 0; i < 5; i++) {
            buffer_defaults(); x = &gpu_boot_inventory.power;
            smmu_mem[GPU_SMMU_SMR/4 + i] = 1;
            gpu_gmu_buffers((vm_offset_t)gmu_mem, (vm_offset_t)smmu_mem, x);
            assert(x->buf.error && !smmu_write_calls && !alloc_calls);
        }
        /* Both measured inert incoming encodings, and refused ABL restores. */
        for (unsigned prior = 0; prior < 3; prior++) {
            buffer_defaults(); x = &gpu_boot_inventory.power;
            if (prior == 1) { smmu_mem[(GPU_SMMU_S2CR+12)/4] = 3; smmu_mem[(GPU_SMMU_CBAR+12)/4] = 0x10000; }
            if (prior == 2) smmu_sticky = 1;
            gpu_gmu_buffers((vm_offset_t)gmu_mem, (vm_offset_t)smmu_mem, x); b = &x->buf;
            assert(!b->error && b->passed == 29 && b->inactive && b->restored == (prior != 2));
        }
        /* Any programming mismatch stops before ATOS and rolls back. */
        const unsigned refuse[] = {GPU_SMMU_CBA2R+12, GPU_SMMU_CBAR+12,
            cb+GPU_SMMU_CB_TCR2, cb+GPU_SMMU_CB_TCR, cb+GPU_SMMU_CB_TTBR0,
            cb+GPU_SMMU_CB_MAIR0, cb+GPU_SMMU_CB_SCTLR, GPU_SMMU_S2CR+12, GPU_SMMU_SMR+12};
        for (unsigned i = 0; i < sizeof(refuse)/sizeof(refuse[0]); i++) {
            buffer_defaults(); x = &gpu_boot_inventory.power; refuse_smmu_off = refuse[i];
            gpu_gmu_buffers((vm_offset_t)gmu_mem, (vm_offset_t)smmu_mem, x); b = &x->buf;
            assert(b->error && !b->checks && b->inactive && b->restored && gmu_mem[0x14000/4] == 1);
        }
        for (unsigned failure = 0; failure < 4; failure++) {
            buffer_defaults(); x = &gpu_boot_inventory.power;
            if (failure == 0) ats_stuck = 1;
            if (failure == 1) tlb_stuck = 1;
            if (failure == 2) bad_atos = 1;
            if (failure == 3) bad_atos = 2;
            gpu_gmu_buffers((vm_offset_t)gmu_mem, (vm_offset_t)smmu_mem, x); b = &x->buf;
            assert(b->error && b->passed < 29 && !smmu_mem[(GPU_SMMU_SMR+12)/4] && !smmu_mem[cb/4]);
            assert(b->inactive == (failure != 1));
            if (failure == 1) assert(b->stage == 1); /* Never enabled before TLB sync. */
        }
        /* Full mode-11 path, default-off isolation and cached replay. */
        buffer_defaults(); mode = 11;
        arc_run(); x = &gpu_boot_inventory.power; b = &x->buf;
        assert(b->passed == 29 && b->inactive && !x->ctx_requested && x->clk_restored);
        assert(strstr(output, "buffers final SMR/S2CR/SCTLR/CBAR="));
        unsigned writes = smmu_write_calls, allocations = alloc_calls;
        sweet_gpu_replay(); assert(smmu_write_calls == (int)writes && alloc_calls == (int)allocations);
        buffer_defaults(); mode = 10; arc_run(); assert(!gpu_boot_inventory.power.buf.requested);
        puts("PASS: GMU buffers 29 ATOS checks, 38 refusal cases, readback/timeout/mapping failures, rollback and replay");
    }

    /* 0094: read-only pre-boot inventory, including every refusal and replay. */
    {
        struct gpu_power_experiment *x;
        uint32_t before[GPU_GMU_SIZE/4], sb[GPU_SMMU_SIZE/4];
        buffer_defaults(); x = &gpu_boot_inventory.power;
        x->buf.requested = x->buf.inactive = 1; x->buf.stage = 3;
        x->buf.passed = x->buf.checks = 29;
        assert(GPU_PREBOOT_READS == 29);
        const uint32_t offsets[] = {0x14730,0x24c1c,0x24c20,0x23404,0x14000,
            0x14004,0x14070,0x14068,0xafe0,0x14614,0x14610,0x24c44,0x140b4,
            0x14608,0x14400,0x14404,0x1303c,0x13000,0x13004,0x14300,0x14304,
            0x14308,0x143a0,0x14714,0x14718,0x1472c,0x24c14,0x14618,0x14600};
        for (unsigned i = 0; i < GPU_PREBOOT_READS; i++) {
            assert(gpu_preboot_regs[i].off == offsets[i] && !(offsets[i] & 3) && offsets[i] < GPU_GMU_SIZE);
            for (unsigned j = 0; j < i; j++) assert(offsets[i] != offsets[j]);
            gmu_mem[offsets[i]/4] = 0xa0a00000u+i;
        }
        gmu_mem[0x14000/4] = 1; gmu_mem[0x14068/4] = 0;
        memcpy(before,gmu_mem,sizeof(before)); memcpy(sb,smmu_mem,sizeof(sb));
        gpu_gmu_preboot_read((vm_offset_t)gmu_mem, x);
        assert(x->preboot_requested && x->preboot_done == 29 && !x->preboot_error && !all_mmio_writes);
        for (unsigned i = 0; i < GPU_PREBOOT_READS; i++) assert(x->preboot_value[i] == before[offsets[i]/4]);
        assert(!memcmp(before,gmu_mem,sizeof(before)) && !memcmp(sb,smmu_mem,sizeof(sb)));
        x->requested = x->clk_requested = 1;
        gpu_power_log(x); assert(strstr(output, "pre-boot GMU read=29/29 result: read-only dump complete"));
        for (unsigned bad = 0; bad < 8; bad++) {
            buffer_defaults(); x = &gpu_boot_inventory.power;
            x->buf.requested = x->buf.inactive = 1; x->buf.stage = 3;
            x->buf.passed = x->buf.checks = 29;
            if (bad == 0) x->buf.requested = 0;
            if (bad == 1) x->buf.error = "test error";
            if (bad == 2) x->buf.stage = 2;
            if (bad == 3) x->buf.passed = 28;
            if (bad == 4) x->buf.checks = 28;
            if (bad == 5) x->buf.inactive = 0;
            if (bad == 6) gmu_mem[0x14000/4] = 0;
            if (bad == 7) gmu_mem[0x14068/4] = 1;
            memcpy(before,gmu_mem,sizeof(before)); memcpy(sb,smmu_mem,sizeof(sb));
            gpu_gmu_preboot_read((vm_offset_t)gmu_mem, x);
            assert(x->preboot_requested && x->preboot_done == 0 && x->preboot_error && !all_mmio_writes);
            assert(!memcmp(before,gmu_mem,sizeof(before)) && !memcmp(sb,smmu_mem,sizeof(sb)));
        }
        /* The observed dirty saved CBAR promotion must be normalized for narrow diagnostics. */
        buffer_defaults(); x = &gpu_boot_inventory.power;
        assert(gpu_buffer_set((vm_offset_t)smmu_mem, &x->buf, GPU_SMMU_CBAR+12, 0xfffffe8f00000000ull, 0));
        assert(x->buf.wrote[0] == 0 && x->buf.got[0] == 0 && smmu_mem[(GPU_SMMU_CBAR+12)/4] == 0);
        buffer_defaults(); mode = 12; arc_run(); x = &gpu_boot_inventory.power;
        assert(x->preboot_done == 29 && !x->preboot_error && x->buf.passed == 29 && x->buf.inactive && x->clk_restored);
        assert(gmu_mem[0x14000/4] == 1 && gmu_mem[0x14004/4] == 0 && gmu_mem[0x14730/4] == 0);
        assert(strstr(output, "pre-boot GMU DTCM_FW_VERSION +0xafe0 ="));
        int writes = all_mmio_writes, allocations = alloc_calls;
        sweet_gpu_replay(); assert(all_mmio_writes == writes && alloc_calls == allocations);
        buffer_defaults(); mode = 11; arc_run(); assert(!gpu_boot_inventory.power.preboot_requested);
        buffer_defaults(); mode = 12; fail_alloc = 1; arc_run();
        assert(gpu_boot_inventory.power.preboot_requested && !gpu_boot_inventory.power.preboot_done);
        buffer_defaults(); mode = 12; fail_gmu_map = 1; arc_run();
        assert(!gpu_boot_inventory.power.preboot_requested);
        buffer_defaults(); mode = 12; fail_smmu_map = 1; arc_run();
        assert(!gpu_boot_inventory.power.preboot_requested);
        puts("PASS: 29 pre-boot registers, 8 refusal cases, read-only isolation, normalization and replay");
    }

    /* 0095: bounded RSC wake/stop before any firmware execution. */
    {
        struct gpu_power_experiment *x;
        struct gpu_rsc_wake *w;
        uint32_t before[GPU_GMU_SIZE/4];
        wake_defaults(); x = &gpu_boot_inventory.power;
        memcpy(before,gmu_mem,sizeof(before));
        gpu_rsc_wake_run((vm_offset_t)gmu_mem,(vm_offset_t)cc,x); w = &x->wake;
        assert(!w->error && w->started && w->ack_done && w->busy_done && w->stop_attempted && w->stop_done);
        assert(w->snapshots == 7 && w->controls_restored && w->state_restored && w->ack_polls == 2 && w->busy_polls == 1 && w->stop_polls == 2);
        const uint32_t off[] = {0x14730,0x24c1c,0x24c1c,0x24c1c,0x24c1c,0x14730};
        const uint32_t val[] = {1,2,0,1,0,0};
        assert(wake_trace_n == 6 && !memcmp(off,wake_trace_off,sizeof(off)) && !memcmp(val,wake_trace_val,sizeof(val)));
        assert(!memcmp(before,gmu_mem,sizeof(before)));
        /* Every metadata gate independently refuses before any MMIO store. */
        for (unsigned bad = 0; bad < 11; bad++) {
            wake_defaults(); x = &gpu_boot_inventory.power;
            if (bad == 0) x->preboot_error = "test error";
            if (bad == 1) x->preboot_done--;
            if (bad == 2) x->buf.inactive = 0;
            if (bad == 3) x->buf.error = "test error";
            if (bad == 4) x->buf.passed--;
            if (bad == 5) x->init_requested = 0;
            if (bad == 6) x->init_done_writes = 0;
            if (bad == 7) x->init_nwrites--;
            if (bad == 8) x->init_stop_done = 0;
            if (bad == 9) x->init_bad--;
            if (bad == 10) x->init_nbad_log--;
            memcpy(before,gmu_mem,sizeof(before));
            gpu_rsc_wake_run((vm_offset_t)gmu_mem,(vm_offset_t)cc,x);
            assert(x->wake.error && !x->wake.started && !all_mmio_writes && !wake_trace_n && !memcmp(before,gmu_mem,sizeof(before)));
        }
        /* No generic mismatch mask: every field of each of the nine signatures matters. */
        for (unsigned i = 0; i < 9; i++) for (unsigned field = 0; field < 4; field++) {
            wake_defaults(); x = &gpu_boot_inventory.power;
            if (field == 0) x->init_bad_region[i] ^= 1;
            if (field == 1) x->init_bad_off[i] ^= 4;
            if (field == 2) x->init_bad_wrote[i] ^= 1;
            if (field == 3) x->init_bad_got[i] ^= 1;
            gpu_rsc_wake_run((vm_offset_t)gmu_mem,(vm_offset_t)cc,x);
            assert(x->wake.error && !all_mmio_writes && !wake_trace_n);
        }
        for (unsigned bad = 0; bad < 10; bad++) {
            wake_defaults(); x = &gpu_boot_inventory.power;
            if (bad < 6) gmu_mem[gpu_wake_off[bad]/4] ^= 4;
            else if (bad == 6) gmu_mem[0x14068/4] = 1;
            else if (bad == 7) cc[GPU_GX_GDSCR/4] ^= GPU_DOMAIN_ON;
            else if (bad == 8) cc[GPU_GX_GDSCR/4] = ~0u;
            else cc[GPU_GX_GDSCR/4] &= ~GPU_GDSC_SW_COLLAPSE;
            memcpy(before,gmu_mem,sizeof(before));
            gpu_rsc_wake_run((vm_offset_t)gmu_mem,(vm_offset_t)cc,x);
            assert(x->wake.error && !all_mmio_writes && !memcmp(before,gmu_mem,sizeof(before)));
        }
        /* Every failed handshake is bounded; clear REQ and restore retention on all paths. */
        for (unsigned fail = 0; fail < 6; fail++) {
            wake_defaults(); x = &gpu_boot_inventory.power;
            if (fail == 0) wake_ack_stuck = 1;
            if (fail == 1) wake_busy_stuck = 1;
            if (fail == 2) wake_stop_stuck = 1;
            if (fail == 3) retention_stuck = 1;
            if (fail == 4) retention_restore_stuck = 1;
            if (fail == 5) wake_gx_on = 1;
            gpu_rsc_wake_run((vm_offset_t)gmu_mem,(vm_offset_t)cc,x); w = &x->wake;
            assert(w->error && gmu_mem[0x24c1c/4] == 0 && gmu_mem[0x14000/4] == 1);
            assert(gmu_mem[0x14730/4] == (fail == 4 ? 1u : 0u));
            assert(w->ack_polls <= 100 && w->busy_polls <= 100 && w->stop_polls <= 100);
            if (fail == 0) assert(!w->ack_done && w->ack_polls == 100 && !w->busy_polls && w->stop_done);
            if (fail == 1) assert(w->ack_done && !w->busy_done && w->busy_polls == 100 && w->stop_done);
            if (fail == 2) assert(w->ack_done && w->busy_done && !w->stop_done && w->stop_polls == 100 && !w->state_restored);
            if (fail == 3) assert(!w->started && !w->stop_attempted && wake_trace_n == 2 && w->controls_restored && w->snapshots == 5);
            if (fail == 4) assert(w->ack_done && w->busy_done && w->stop_done && !w->controls_restored);
            if (fail == 5) assert(w->stop_done && w->controls_restored && (w->gx[1] & GPU_DOMAIN_ON));
        }
        /* Full source path models the exact known readbacks, plus lower-mode and replay isolation. */
        wake_defaults(); gmu_mem[0x24c20/4] = gmu_mem[0x23404/4] = gmu_mem[0x23010/4] = 0;
        arc_run(); x = &gpu_boot_inventory.power; w = &x->wake;
        assert(!w->error && w->state_restored && x->buf.inactive && x->clk_restored && gmu_mem[0x14000/4] == 1);
        assert(strstr(output,"wake/stop complete; CM3 stayed in reset"));
        int writes = all_mmio_writes; sweet_gpu_replay(); assert(writes == all_mmio_writes);
        wake_defaults(); mode = 12; gmu_mem[0x24c20/4] = gmu_mem[0x23404/4] = 0;
        arc_run(); assert(!gpu_boot_inventory.power.wake.requested && !wake_seen);
        puts("PASS: RSC wake/stop, 57 zero-write refusal cases, bounded failures and reset preservation");
    }

    /* 0096: IRQ/fence preflight is read-only, every gate independently refused. */
    {
        struct gpu_power_experiment *x;
        uint32_t before[GPU_GMU_SIZE/4], sb[GPU_SMMU_SIZE/4];
        const uint32_t off[] = {0x24c18,0x1464c,0x14648,0x24c14,0x24c40,0x143b0};
        for (unsigned bad = 0; bad <= 13; bad++) {
            wake_defaults(); x = &gpu_boot_inventory.power;
            x->wake.ack_done = x->wake.busy_done = x->wake.stop_done = 1;
            x->wake.controls_restored = x->wake.state_restored = 1;
            for (unsigned i = 0; i < 6; i++) {
                assert(gpu_irq_preflight_regs[i].off == off[i] && off[i] < GPU_GMU_SIZE && !(off[i] & 3));
                gmu_mem[off[i]/4] = 0x9a000000u+i;
            }
            /* All-ones is a legitimate interrupt mask; preserve, never "fix" it. */
            gmu_mem[off[0]/4] = ~0u;
            switch (bad) {
            case 0: break;
            case 1: x->wake.error = "test error"; break;
            case 2: x->wake.ack_done = 0; break;
            case 3: x->wake.busy_done = 0; break;
            case 4: x->wake.stop_done = 0; break;
            case 5: x->wake.controls_restored = 0; break;
            case 6: x->wake.state_restored = 0; break;
            case 7: x->preboot_error = "test error"; break;
            case 8: x->preboot_done--; break;
            case 9: x->buf.error = "test error"; break;
            case 10: x->buf.inactive = 0; break;
            case 11: x->buf.passed--; break;
            case 12: gmu_mem[0x14000/4] = 0; break;
            case 13: gmu_mem[0x14068/4] = 1; break;
            }
            memcpy(before,gmu_mem,sizeof(before)); memcpy(sb,smmu_mem,sizeof(sb));
            gpu_gmu_irq_preflight((vm_offset_t)gmu_mem,x);
            assert(x->irq_preflight_requested && !all_mmio_writes);
            assert(!memcmp(before,gmu_mem,sizeof(before)) && !memcmp(sb,smmu_mem,sizeof(sb)));
            if (bad) assert(x->irq_preflight_error && !x->irq_preflight_done);
            else {
                assert(!x->irq_preflight_error && x->irq_preflight_done == 6);
                for (unsigned i = 0; i < 6; i++) assert(x->irq_preflight_value[i] == before[off[i]/4]);
            }
        }
        wake_defaults(); mode = 14; gmu_mem[0x24c20/4] = gmu_mem[0x23404/4] = gmu_mem[0x23010/4] = 0;
        arc_run(); x = &gpu_boot_inventory.power;
        assert(x->irq_preflight_done == 6 && !x->irq_preflight_error && x->clk_restored && x->buf.inactive);
        assert(gmu_mem[0x14000/4] == 1 && strstr(output,"masks/fence unchanged; CM3 held reset"));
        int writes = all_mmio_writes; sweet_gpu_replay(); assert(writes == all_mmio_writes);
        wake_defaults(); mode = 13; gmu_mem[0x24c20/4] = gmu_mem[0x23404/4] = 0;
        arc_run(); assert(!gpu_boot_inventory.power.irq_preflight_requested);
        wake_defaults(); mode = 14; gmu_mem[0x24c20/4] = gmu_mem[0x23404/4] = 0; wake_ack_stuck = 1;
        arc_run(); assert(gpu_boot_inventory.power.irq_preflight_requested && !gpu_boot_inventory.power.irq_preflight_done);
        puts("PASS: six IRQ/fence reads, 13 zero-write refusals, mode isolation, reset and replay");
    }

    /* 0097: exact four writes, independent refusal gates, partial-write cleanup. */
    {
        struct gpu_power_experiment *x;
        struct gpu_irq_mask_probe *m;
        uint32_t before[GPU_GMU_SIZE/4], sb[GPU_SMMU_SIZE/4];
        const unsigned off[] = {0x24c18,0x1464c,0x14648,0x24c14,0x24c40,0x143b0};
        for (unsigned bad = 0; bad <= 20; bad++) {
            irq_defaults(); x = &gpu_boot_inventory.power;
            if (bad == 1) x->irq_preflight_error = "test error";
            if (bad == 2) x->irq_preflight_done--;
            if (bad >= 3 && bad <= 8) x->irq_preflight_value[bad-3] ^= 1;
            if (bad >= 9 && bad <= 14) gmu_mem[off[bad-9]/4] ^= 1;
            if (bad == 15) gmu_mem[0x14000/4] = 0;
            if (bad == 16) gmu_mem[0x14068/4] = 1;
            if (bad == 17) gmu_mem[0x14070/4] = 1;
            if (bad == 18) cc[GPU_GX_GDSCR/4] = ~0u;
            if (bad == 19) cc[GPU_GX_GDSCR/4] |= GPU_DOMAIN_ON;
            if (bad == 20) cc[GPU_GX_GDSCR/4] &= ~GPU_GDSC_SW_COLLAPSE;
            memcpy(before,gmu_mem,sizeof(before)); memcpy(sb,smmu_mem,sizeof(sb));
            gpu_gmu_irq_mask_test((vm_offset_t)gmu_mem,(vm_offset_t)cc,x); m=&x->irq_mask;
            assert(m->requested && !memcmp(before,gmu_mem,sizeof(before)) && !memcmp(sb,smmu_mem,sizeof(sb)));
            if (bad) assert(m->error && !m->attempted && !all_mmio_writes && !irq_trace_n);
            else {
                assert(!m->error && m->attempted == 2 && m->masked == 2 && m->restored && !m->quarantined);
                assert(irq_trace_n == 4 && all_mmio_writes == 4 && m->nwrites == 4);
                const unsigned wo[] = {0x24c18,0x1464c,0x1464c,0x24c18};
                for (unsigned i = 0; i < 4; i++) {
                    assert(irq_trace_off[i] == wo[i] && irq_trace_value[i] == (i < 2 ? ~0u : 0));
                    assert(m->off[i] == wo[i] && m->wrote[i] == irq_trace_value[i] && m->got[i] == (i == 0 ? 0x3fu : m->wrote[i]));
                }
                assert(m->masked_value[0] == 0x3fu && m->masked_value[1] == ~0u);
                assert(m->reset == 1 && !m->busy && !m->init && m->gx_before == m->gx_final);
            }
        }
        /* Each write can fail, including either restore; no later mask/start on failure. */
        for (unsigned fail = 1; fail <= 4; fail++) {
            irq_defaults(); x=&gpu_boot_inventory.power; irq_fail_write = fail;
            gpu_gmu_irq_mask_test((vm_offset_t)gmu_mem,(vm_offset_t)cc,x); m=&x->irq_mask;
            assert(m->error && gmu_mem[0x14000/4] == 1 && !m->quarantined);
            if (fail <= 2) {
                assert(m->restored && m->masked == fail-1 && m->attempted == fail && irq_trace_n == 2*fail);
                assert(!gmu_mem[0x24c18/4] && !gmu_mem[0x1464c/4]);
            } else {
                assert(!m->restored && m->masked == 2 && irq_trace_n == 4);
                assert(gmu_mem[(fail == 3 ? 0x1464c : 0x24c18)/4] == (fail == 3 ? ~0u : 0x3fu));
            }
        }
        /* Pending status/reset/idle changes forbid unmasking; preserve evidence. */
        for (unsigned change = 1; change <= 8; change++) {
            irq_defaults(); x=&gpu_boot_inventory.power; irq_change = change;
            gpu_gmu_irq_mask_test((vm_offset_t)gmu_mem,(vm_offset_t)cc,x); m=&x->irq_mask;
            assert(m->error && !m->restored && irq_trace_n == 4);
            if (change <= 5) {
                assert(m->quarantined && gmu_mem[0x24c18/4] == 0x3fu && gmu_mem[0x1464c/4] == ~0u);
                for (unsigned i = 0; i < 4; i++) assert(irq_trace_value[i] == ~0u);
            } else assert(!m->quarantined && !gmu_mem[0x24c18/4] && !gmu_mem[0x1464c/4]);
        }
        /* 0098: only the measured AO tuple is accepted; no ignored-bit mask. */
        for (unsigned bad = 0; bad < 9; bad++) {
            irq_defaults(); x=&gpu_boot_inventory.power;
            irq_ao_readback = bad < 6 ? 0x3fu & ~(1u << bad) : bad == 6 ? 0x7fu : bad == 7 ? 0x8000003fu : ~0u;
            gpu_gmu_irq_mask_test((vm_offset_t)gmu_mem,(vm_offset_t)cc,x); m=&x->irq_mask;
            assert(m->error && m->attempted == 1 && !m->masked && m->restored && irq_trace_n == 2);
            assert(!gmu_mem[0x24c18/4] && !gmu_mem[0x1464c/4] && gmu_mem[0x14000/4] == 1);
        }
        /* The same 0x3f readback is NOT accepted for HFI; reject every missing bit. */
        for (unsigned bad = 0; bad <= 32; bad++) {
            irq_defaults(); x=&gpu_boot_inventory.power;
            irq_hfi_readback = bad < 32 ? ~(1u << bad) : 0x3fu;
            gpu_gmu_irq_mask_test((vm_offset_t)gmu_mem,(vm_offset_t)cc,x); m=&x->irq_mask;
            assert(m->error && m->attempted == 2 && m->masked == 1 && m->restored && irq_trace_n == 4);
            assert(!gmu_mem[0x24c18/4] && !gmu_mem[0x1464c/4] && gmu_mem[0x14000/4] == 1);
        }
        /* Full chain, mode isolation and cached replay never redo writes. */
        irq_defaults(); gmu_mem[0x24c20/4] = gmu_mem[0x23404/4] = gmu_mem[0x23010/4] = 0;
        arc_run(); x=&gpu_boot_inventory.power; m=&x->irq_mask;
        assert(!m->error && m->masked == 2 && m->restored && irq_trace_n == 4);
        assert(x->irq_preflight_done == 6 && !x->irq_preflight_error && x->wake.state_restored && x->buf.inactive && x->clk_restored);
        assert(gmu_mem[0x14000/4] == 1 && strstr(output,"both sources masked and restored; CM3 stayed reset"));
        int writes = all_mmio_writes; sweet_gpu_replay(); assert(writes == all_mmio_writes);
        irq_defaults(); mode = 14; gmu_mem[0x24c20/4] = gmu_mem[0x23404/4] = gmu_mem[0x23010/4] = 0;
        arc_run(); assert(!gpu_boot_inventory.power.irq_mask.requested && !irq_trace_n);
        irq_defaults(); gmu_mem[0x24c20/4] = gmu_mem[0x23404/4] = gmu_mem[0x23010/4] = 0; wake_ack_stuck = 1;
        arc_run(); assert(gpu_boot_inventory.power.irq_mask.error && !irq_trace_n);
        puts("PASS: interrupt mask/restore, exact AO 0x3f tuple and 42 rejected alternatives, 20 zero-write refusals, all write failures, quarantine, mode and replay");
    }

    /* Mode 3 never runs the clock stage. */
    arc_reset(); mode = 3; cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; arc_run();
    assert(!gpu_boot_inventory.power.clk_requested);
    assert(cc[GPU_CC_CX_GMU / 4] == 0x80004220u && cc[GPU_GMU_RCG_CFG / 4] == 0x100u);
    /* Mode 2 never reaches the experiment. */
    arc_reset(); cc[GPU_CX_GDSCR / 4] = GPU_CX_IDLE_GDSCR; arc_run();
    assert(!gpu_boot_inventory.power.requested && vote_count == 0 && delay_calls == 0);
    puts("PASS: 14 clock/cache cases, 30 ARC cases + 512 mutations, 61 CX experiment cases");

    /* FP6 is a separate read-only GPUCC inventory; the default SWEET probe
     * and all SWEET register profiles remain unchanged. */
    memset(fp6_gpucc, 0, sizeof(fp6_gpucc));
    for (unsigned i = 0; i < sizeof(fp6_gpucc) / sizeof(fp6_gpucc[0]); i++)
        fp6_gpucc[i] = 0x5a000000u ^ i;
    memcpy(fp6_gpucc_before, fp6_gpucc, sizeof(fp6_gpucc));
    fp6_mode = 0; fp6_gpu_inventory();
    assert(fp6_map_calls == 0 && memcmp(fp6_gpucc_before, fp6_gpucc, sizeof(fp6_gpucc)) == 0);
    fp6_mode = 2; fp6_gpu_inventory();
    assert(fp6_map_calls == 0);
    fp6_mode = 1; fp6_gpu_inventory();
    assert(fp6_map_calls == 1);
    assert(strstr(output, "unsupported fp6gpu=2"));
    assert(strstr(output, "FP6 Adreno 810 Gen8.3 GPUCC inventory"));
    assert(strstr(output, "GPU core, GMU and SMMU not mapped"));
    assert(memcmp(fp6_gpucc_before, fp6_gpucc, sizeof(fp6_gpucc)) == 0);
    puts("PASS: FP6 GPUCC inventory is opt-in, read-only, and bounded");

    /* The dedicated FP6 SMMU route inventory is also opt-in and read-only. */
    memset(fp6_smmu, 0, sizeof(fp6_smmu));
    fp6_smmu_maps = 0; fp6_smmu_mode = 0;
    fp6_smmu_inventory();
    assert(fp6_smmu_maps == 0);
    fp6_smmu_mode = 1;
    fp6_smmu[0x20 / 4] = (1u << 27) | 8u; /* stream matching, 8 groups */
    fp6_smmu[0x24 / 4] = (1u << 28) | 8u; /* 4 KiB pages, 8 context banks */
    fp6_smmu[0x800 / 4] = 0x80000005u; /* valid SID 5 */
    fp6_smmu[0xc00 / 4] = 2u; /* translate through CB2 */
    fp6_smmu[0x1000 / 4 + 2] = 0x1234u;
    fp6_smmu[0x1800 / 4 + 2] = 0x5678u;
    fp6_smmu[0x6000 / 4] = 0x1u;
    int writes_before_smmu_inventory = all_mmio_writes;
    fp6_smmu_inventory();
    assert(fp6_smmu_maps == 1 && all_mmio_writes == writes_before_smmu_inventory);
    assert(strstr(output, "group=0 valid=1 SMR=0x80000005 ID=0x5 MASK=0x0"));
    assert(strstr(output, "CB2 CBAR=0x00001234 CBA2R=0x00005678"));
    assert(strstr(output, "read-only inventory complete; no writes or ATOS requests"));
    puts("PASS: FP6 GPU SMMU route inventory is opt-in and read-only");

    /* Read the SMMU global-fault SPI state from the GIC distributor; no write,
     * clear, affinity change, or firmware start is permitted in this probe. */
    memset(fp6_gicd, 0, sizeof(fp6_gicd));
    fp6_smmu_irq_mode = 0; fp6_gicd_maps = 0; fail_fp6_gicd_map = 0;
    fp6_smmu_fault_irq_inventory();
    assert(fp6_gicd_maps == 0);
    fp6_smmu_irq_mode = 2;
    fp6_smmu_fault_irq_inventory();
    assert(fp6_gicd_maps == 0 && strstr(output, "unsupported fp6smmuirq=2"));
    fp6_smmu_irq_mode = 1; fail_fp6_gicd_map = 1;
    fp6_smmu_fault_irq_inventory();
    assert(fp6_gicd_maps == 1 && strstr(output, "distributor map failed"));
    fail_fp6_gicd_map = 0;
    fp6_gicd[0x004/4] = 0x00000007u; /* GICD_TYPER */
    fp6_gicd[0x158/4] = 1u << 1;     /* INTID 705 enabled */
    fp6_gicd[0x258/4] = 0;           /* no pending global fault */
    fp6_gicd[0xcb0/4] = 2u << 2;     /* SPI level/edge config field for INTID 705 */
    uint32_t gic_before[0x10000/4]; memcpy(gic_before, fp6_gicd, sizeof(gic_before));
    int gic_writes_before = all_mmio_writes;
    fp6_smmu_fault_irq_inventory();
    assert(fp6_gicd_maps == 2 && all_mmio_writes == gic_writes_before);
    assert(!memcmp(gic_before, fp6_gicd, sizeof(gic_before)));
    assert(strstr(output, "INTID=705") && strstr(output, "enabled=1 edge=1"));
    puts("PASS: FP6 SMMU global IRQ inventory is opt-in, read-only, and bounded");

    /* Clock prerequisites use the exact stock DT consumer order, borrow the
     * powered CX domain, and release only enable votes acquired here. */
    memset(fp6_gpucc, 0, sizeof(fp6_gpucc));
    memset(fp6_gcc_gpu, 0, sizeof(fp6_gcc_gpu));
    struct fp6_smmu_clocks clocks = {0};
    all_mmio_writes = 0;
    assert(!fp6_smmu_clocks_get(&clocks) && all_mmio_writes == 0);
    fp6_gpucc[0x9094/4] = 0x80000000u;   /* CX on: status register PWR_ON */
    fp6_gpucc[0x93ec/4] = 0x80000000u;
    assert(!fp6_smmu_clocks_get(&clocks) && all_mmio_writes == 0);
    fp6_gpucc[0x93ec/4] = 0;
    fp6_gcc_gpu[0x10/4] = 2; /* HWCG remains untouched. */
    assert(fp6_smmu_clocks_get(&clocks));
    assert(fp6_gpucc[0x7000/4] == 1 && fp6_gpucc[0x90bc/4] == 1);
    assert(fp6_gcc_gpu[0x10/4] == 3 && fp6_gcc_gpu[0x18/4] == 1);
    fp6_smmu_clocks_put(&clocks);
    assert(fp6_gpucc[0x7000/4] == 0 && fp6_gpucc[0x90bc/4] == 0);
    assert(fp6_gcc_gpu[0x10/4] == 2 && fp6_gcc_gpu[0x18/4] == 0);
    /* A refused enable on a branch that reports CLK_OFF is a failure. */
    static uint32_t * const refuse_reg[4] = { &fp6_gpucc[0x7000/4], &fp6_gcc_gpu[0x10/4],
                                              &fp6_gcc_gpu[0x18/4], &fp6_gpucc[0x90bc/4] };
    for (unsigned n = 0; n < 4; n++) {
        uint32_t saved = *refuse_reg[n];
        *refuse_reg[n] = saved | 0x80000000u;
        fp6_clock_refuse = (int)n;
        assert(!fp6_smmu_clocks_get(&clocks));
        *refuse_reg[n] = saved;
        assert(!clocks.acquired && fp6_gpucc[0x7000/4] == 0 && fp6_gpucc[0x90bc/4] == 0);
        assert(fp6_gcc_gpu[0x10/4] == 2 && fp6_gcc_gpu[0x18/4] == 0);
    }
    /* FP6 gpu_cc_ahb: enable ignored but CLK_OFF clear (running): accepted. */
    fp6_clock_refuse = 3;
    fp6_gpucc[0x90bc/4] = 0;
    assert(fp6_smmu_clocks_get(&clocks));
    fp6_smmu_clocks_put(&clocks);
    fp6_gpucc[0x7000/4] = 0;
    fp6_gcc_gpu[0x18/4] = 0;
    fp6_clock_refuse = -1;
    fp6_gpucc[0x7000/4] = fp6_gpucc[0x90bc/4] = 1;
    fp6_gcc_gpu[0x10/4] = 3; fp6_gcc_gpu[0x18/4] = 1;
    all_mmio_writes = 0;
    assert(fp6_smmu_clocks_get(&clocks)); fp6_smmu_clocks_put(&clocks);
    assert(all_mmio_writes == 0); /* Preserve all four borrowed votes. */
    puts("PASS: FP6 SMMU stock clock prerequisite votes and rollback");

    /* FP6 RSCv3 command layout and actual CX/hub enable sequence. */
    memset(fp6_cmd_db, 0, sizeof(fp6_cmd_db));
    uint32_t arc_address = 0, arc_level = 0;
    assert(!fp6_arc_level((vm_offset_t)fp6_cmd_db, 0, &arc_address, &arc_level));
    fp6_cmd_db[4/4] = 0x0c0330dbu;
    fp6_cmd_db[8/4] = (0x100u << 16) | 3u;
    fp6_cmd_db[12/4] = (1u << 16) | 0x180u;
    fp6_cmd_db[0x190/4] = 0x6c2e7863u;
    fp6_cmd_db[0x194/4] = 0x00006c76u;
    fp6_cmd_db[0x1a0/4] = 0x30000u;
    fp6_cmd_db[0x1a4/4] = 6u;
    fp6_cmd_db[0x210/4] = 64u << 16;
    fp6_cmd_db[0x214/4] = 0x180u;
    assert(fp6_arc_level((vm_offset_t)fp6_cmd_db, 0, &arc_address, &arc_level));
    /* LOW_SVS floor: aux levels {0, 64, 0x180} -> index 1, not TURBO's 2. */
    assert(arc_address == 0x30000u && arc_level == 1);
    fp6_rsc[0] = 3u << 16;
    fp6_rsc[0x0c/4] = (16u << 27) | (8u << 12);
    fp6_rsc[(0xd00+0x28)/4] = 1;
    fp6_gpucc[0x9080/4] = 0xf001u;       /* collapsed, clk-dis-wait 0xf */
    fp6_gpucc[0x9094/4] = 0;
    fp6_gpucc[0x93ec/4] = 0x80000000u;
    fp6_power_mode = 1;
    assert(fp6_smmu_clocks_get(&clocks));
    /* SW_COLLAPSE cleared, clk-dis-wait 8, RETAIN_FF set; PWR_ON in status. */
    assert(fp6_gpucc[0x9080/4] == 0x8800u);
    assert(fp6_gpucc[0x9094/4] == 0x80000000u);
    assert(fp6_gpucc[0x93f0/4] == 0x100001u);
    assert(fp6_gpucc[0x93ec/4] == 2);
    assert(fp6_rsc[(0xd00+0x38)/4] == 0x30000u);
    assert(fp6_rsc[(0xd00+0x3c)/4] == 1);
    assert(fp6_rsc[(0xd00+0x24)/4] == 0 && fp6_rsc[(0xd00+0x2c)/4] == 0);
    fp6_smmu_clocks_put(&clocks);
    fp6_power_mode = 0;
    puts("PASS: FP6 RSCv3 CX ARC floor, GDSC and hub safe clock enable");

    /* fp6smmu=2: map one 4 KiB GMU SID5 IOVA, verify by ATOS, then roll back. */
    memset(fp6_smmu, 0, sizeof(fp6_smmu));
    fp6_smmu[0x20/4] = (1u << 27) | 24u;
    fp6_smmu[0x24/4] = (4u << 28) | 22u;
    fp6_smmu[0x28/4] = 0x5511u;
    fp6_smmu[0x3c/4] = 0x24u;
    fp6_smmu[0x00/4] = 0x002c0406u;
    for (unsigned i = 0; i < 24; i++) fp6_smmu[(0xc00 + 4*i)/4] = 0x00020000u;
    fp6_smmu_mode = 2; fp6_last_ats = 0; fake_pa_base = 0x90000000ull;
    fp6_seen_tcr2 = fp6_seen_cbar = fp6_seen_fsr_clear = 0;
    fail_alloc = 0; alloc_calls = clean_calls = 0; all_mmio_writes = 0;
    output[0] = 0;
    fp6_smmu_inventory();
    assert(alloc_calls == 1 && clean_calls == 1 && clean_bytes == 0x3000);
    assert(fp6_ats64_writes == 1);
    assert(all_mmio_writes > 0 && strstr(output, "context-bank ATOS IOVA=0x60000000"));
    assert(fp6_seen_tcr2 == 0x00038011u && fp6_seen_cbar == 0x0001f300u && fp6_seen_fsr_clear);
    assert(strstr(output, "passed=1") && strstr(output, "contained=1 route_live=0 bank_reserved=1"));
    assert(fp6_smmu[0x800/4] == 0 && fp6_smmu[0xc00/4] == 0x00020000u);
    assert(strstr(output, "cb=2"));
    assert(fp6_smmu[0x20000/4] == 0 && fp6_smmu[0x20004/4] == 0);
    assert(fp6_smmu[(FP6_TEST_CB_BASE+0x00)/4] == 0 &&
        fp6_smmu[(FP6_TEST_CB_BASE+0x20)/4] == 0 &&
        fp6_smmu[(FP6_TEST_CB_BASE+0x30)/4] == 0 &&
        fp6_smmu[(0x1000+4*FP6_TEST_CB)/4] == 0x0001f300u &&
        fp6_smmu[(0x1800+4*FP6_TEST_CB)/4] == 1);
    assert(dma_rd64(fake_pa_base + 8) == ((fake_pa_base + 0x1000) | 3));
    assert(dma_rd64(fake_pa_base + 0x1000 + 8*256) == ((fake_pa_base + 0x2000) | 3));
    assert(dma_rd64(fake_pa_base + 0x2000) == ((fake_pa_base + 0x3000) | (3ull | (1ull<<10) | (2ull<<8) | (1ull<<6) | (1ull<<11) | (1ull<<54))));
    puts("PASS: FP6 CB2 4 KiB context maps by ATOS and disables its stream match");

    /* ATOSNS means ATS1PR/PAR are unavailable; use the CPU table walker. */
    memset(fp6_smmu, 0, sizeof(fp6_smmu));
    fp6_smmu[0x20/4] = (1u << 27) | (1u << 26) | 24u;
    fp6_smmu[0x24/4] = (4u << 28) | 22u;
    fp6_smmu[0x28/4] = 0x5511u;
    fp6_smmu[0x3c/4] = 0x24u;
    fp6_smmu[0x00/4] = 0x002c0406u;
    for (unsigned i = 0; i < 24; i++) fp6_smmu[(0xc00 + 4*i)/4] = 0x00020000u;
    fp6_smmu_mode = 2; fp6_ats64_writes = 0; fake_pa_base = 0x90000000ull;
    fp6_seen_tcr2 = fp6_seen_cbar = fp6_seen_fsr_clear = 0;
    fail_alloc = 0; alloc_calls = clean_calls = 0; all_mmio_writes = 0;
    output[0] = 0;
    fp6_smmu_inventory();
    assert(alloc_calls == 1 && clean_calls == 1 && clean_bytes == 0x3000);
    assert(fp6_ats64_writes == 0);
    assert(strstr(output, "IDR0.ATOSNS (no ATOS); table walk IOVA=0x60000000"));
    assert(strstr(output, "PA=0x90003000 expected=0x90003000 passed=1"));
    assert(fp6_seen_tcr2 == 0x00038011u && fp6_seen_cbar == 0x0001f300u && fp6_seen_fsr_clear);
    assert(strstr(output, "contained=1 route_live=0 bank_reserved=1"));
    assert(fp6_smmu[0x800/4] == 0 && fp6_smmu[0xc00/4] == 0x00020000u);
    puts("PASS: FP6 ATOSNS path walks 4 KiB tables and issues no ATS request");

    /* Persistent table lookup derives L2/L3 slots directly from the IOVA. */
    struct fp6_gmu_domain lookup_domain = {0};
    uint64_t root_page[512] = {0}, l2_page[512] = {0}, l3_page[512] = {0};
    const uint32_t lookup_iova = 0x60000000u;
    lookup_domain.root.va = (uint8_t *)root_page; lookup_domain.root.pa = 0x1000;
    lookup_domain.l2[1].va = (uint8_t *)l2_page; lookup_domain.l2[1].pa = 0x2000;
    lookup_domain.l3[1][256].va = (uint8_t *)l3_page; lookup_domain.l3[1][256].pa = 0x3000;
    assert(fp6_domain_table_map(&lookup_domain, 0x1000, lookup_iova, 1) == root_page);
    assert(fp6_domain_table_map(&lookup_domain, 0x2000, lookup_iova, 2) == l2_page);
    assert(fp6_domain_table_map(&lookup_domain, 0x3000, lookup_iova, 3) == l3_page);
    assert(fp6_domain_table_map(&lookup_domain, 0x4000, lookup_iova, 3) == NULL);
    puts("PASS: persistent table lookup uses direct L1/L2/L3 indices");

    /* Failure on each first-write stage aborts and disables the stream route. */
    const unsigned fp6_stage_writes[] = {0x1808,0x1008,0x22010,0x22030,
        0x22020,0x22024,0x22038,0x2203c,0x22000,0xc00,0x800};
    for (unsigned n = 0; n < sizeof(fp6_stage_writes)/sizeof(fp6_stage_writes[0]); n++) {
        memset(fp6_smmu, 0, sizeof(fp6_smmu));
        fp6_smmu[0x20/4] = (1u << 27) | 24u;
        fp6_smmu[0x24/4] = (4u << 28) | 22u;
        fp6_smmu[0x28/4] = 0x5511u; fp6_smmu[0x00/4] = 0x002c0406u;
        for (unsigned i = 0; i < 24; i++) fp6_smmu[(0xc00 + 4*i)/4] = 0x00020000u;
        fp6_smmu_mode = 2; fp6_last_ats = 0; fail_alloc = 0;
        alloc_calls = 0; all_mmio_writes = 0; output[0] = 0;
        fp6_refuse_off = fp6_stage_writes[n]; fp6_refuse_nth = 1; fp6_refuse_count = 0;
        fp6_smmu_inventory();
        if (n != 5 && n != 7) { /* refusing a zero write leaves the same readback */
            char diagnostic[128];
            snprintf(diagnostic, sizeof(diagnostic), "setup failed: register readback +0x%x", fp6_stage_writes[n]);
            assert(strstr(output, diagnostic));
            assert(!strstr(output, "context-bank ATOS IOVA="));
        } else {
            assert(!strstr(output, "setup failed:"));
            assert(strstr(output, "passed=1"));
        }
        assert(strstr(output, "contained=1 route_live=0 bank_reserved=1"));
        assert(fp6_smmu[0x800/4] == 0 && fp6_smmu[0xc00/4] == 0x00020000u);
        assert(fp6_smmu[(FP6_TEST_CB_BASE+0)/4] == 0 && fp6_smmu[0x800/4] == 0 &&
            fp6_smmu[0xc00/4] == 0x00020000u);
    }
    fp6_refuse_off = 0; fp6_refuse_nth = fp6_refuse_count = 0;
    puts("PASS: FP6 SMMU write-stage failures leave no active stream match");

    /* SID5 conflict and bad granule geometry must refuse before allocation or writes. */
    for (unsigned refusal = 0; refusal < 2; refusal++) {
        memset(fp6_smmu, 0, sizeof(fp6_smmu));
        fp6_smmu[0x20/4] = (1u << 27) | 24u;
        fp6_smmu[0x24/4] = (4u << 28) | 22u;
        fp6_smmu[0x28/4] = 0x5511u;
        fp6_smmu[0x00/4] = 0x002c0406u;
        for (unsigned i = 0; i < 24; i++) fp6_smmu[(0xc00 + 4*i)/4] = 0x00020000u;
        if (refusal == 0) { fp6_smmu[0x800/4] = 0x80000005u; fp6_smmu[0xc00/4] = 0; }
        else fp6_smmu[0x28/4] &= ~(1u << 12);
        alloc_calls = 0; all_mmio_writes = 0; output[0] = 0;
        fp6_smmu_inventory();
        assert(alloc_calls == 0 && all_mmio_writes == 0);
        assert(strstr(output, refusal == 0 ? "SID5 already has a stream match" : "unsupported geometry"));
    }
    /* Allocation failure also has no SMMU writes. */
    memset(fp6_smmu, 0, sizeof(fp6_smmu));
    fp6_smmu[0x20/4] = (1u << 27) | 24u;
    fp6_smmu[0x24/4] = (4u << 28) | 22u;
    fp6_smmu[0x28/4] = 0x5511u; fp6_smmu[0x00/4] = 0x002c0406u;
    for (unsigned i = 0; i < 24; i++) fp6_smmu[(0xc00 + 4*i)/4] = 0x00020000u;
    fail_alloc = 1; alloc_calls = 0; all_mmio_writes = 0; output[0] = 0;
    fp6_smmu_inventory();
    assert(alloc_calls == 1 && all_mmio_writes == 0 && strstr(output, "allocation failed"));
    fail_alloc = 0;

    /* The PAS probe only checks SCM call availability and PAS ID 13. */
    scm_calls = 0; fp6_pas_mode = 0; fp6_qcom_pas_probe();
    assert(scm_calls == 0);
    fp6_pas_mode = 2; fp6_qcom_pas_probe();
    assert(scm_calls == 0 && strstr(output, "unsupported fp6pas=2"));
    fp6_pas_mode = 1;
    scm_status[0] = 0; scm_value[0] = 1;
    scm_status[1] = 0; scm_value[1] = 1;
    fp6_qcom_pas_probe();
    assert(scm_calls == 2);
    assert(scm_fid[0] == 0xC2000601ULL && scm_arginfo[0] == 1);
    assert(scm_arg0[0] == 0x02000207ULL);
    assert(scm_fid[1] == 0xC2000207ULL && scm_arginfo[1] == 1 && scm_arg0[1] == 13);
    assert(strstr(output, "GPU PAS ID 13 supported=1 (query only)"));

    scm_calls = 0; scm_status[0] = 0; scm_value[0] = 0;
    fp6_qcom_pas_probe();
    assert(scm_calls == 1 && strstr(output, "PAS_IS_SUPPORTED service not advertised"));
    scm_calls = 0; scm_status[0] = 0xFFFFFFFFULL; scm_value[0] = 1;
    fp6_qcom_pas_probe();
    assert(scm_calls == 1 && strstr(output, "call-availability query failed"));
    scm_calls = 0; scm_status[0] = 0; scm_value[0] = 1;
    scm_status[1] = 0xFFFFFFFFULL; scm_value[1] = 0;
    fp6_qcom_pas_probe();
    assert(scm_calls == 2 && strstr(output, "PAS ID 13 query failed"));
    puts("PASS: FP6 Qualcomm SCM PAS query is opt-in and never authenticates firmware");

    /* The signed ZAP loader is separately opt-in and uses the stock no-map carveout. */
    fp6_zap_mode = 0; scm_calls = scm_full_calls = 0; fp6_qcom_pas_zap_load();
    assert(scm_calls == 0 && scm_full_calls == 0);
    fp6_zap_mode = 2; fp6_qcom_pas_zap_load();
    assert(scm_calls == 0 && scm_full_calls == 0 && strstr(output, "unsupported fp6zap=2"));
    fp6_zap_mode = 1; scm_status[0] = 0xFFFFFFFFULL; scm_value[0] = 1;
    scm_calls = scm_full_calls = 0; fp6_qcom_pas_zap_load();
    assert(scm_calls == 1 && scm_full_calls == 0);
    scm_status[0] = 0; scm_value[0] = 1; scm_status[1] = 0; scm_value[1] = 0;
    scm_calls = scm_full_calls = 0; fp6_qcom_pas_zap_load();
    assert(scm_calls == 2 && scm_full_calls == 0);
    scm_status[0] = scm_status[1] = 0;
    scm_value[0] = scm_value[1] = 1; zap_map_fail = 1; scm_calls = scm_full_calls = 0;
    fp6_qcom_pas_zap_load();
    assert(scm_calls == 2 && scm_full_calls == 0 && strstr(output, "reserved-memory map failed"));
    zap_map_fail = 0;
    for (unsigned fail = 1; fail <= 3; fail++) {
        memset(zap_region, 0, sizeof(zap_region));
        scm_calls = scm_full_calls = 0; scm_full_fail_at = fail;
        fp6_qcom_pas_zap_load();
        assert(scm_calls == 2 && scm_full_calls == fail + 1);
        assert(scm_full[scm_full_calls - 1].fid == 0xC2000206ULL);
        assert(scm_full[scm_full_calls - 1].arginfo == 1);
        assert(scm_full[scm_full_calls - 1].arg0 == 13);
    }
    memset(zap_region, 0, sizeof(zap_region));
    scm_calls = scm_full_calls = 0; scm_full_fail_at = 0;
    fp6_qcom_pas_zap_load();
    assert(scm_calls == 2 && scm_full_calls == 3);
    assert(scm_full[0].fid == 0xC2000201ULL && scm_full[0].arginfo == 0x82);
    assert(scm_full[0].arg0 == 13 && scm_full[0].arg1 == 0x9ea9b000ULL);
    assert(scm_full[1].fid == 0xC2000202ULL && scm_full[1].arginfo == 3);
    assert(scm_full[1].arg0 == 13 && scm_full[1].arg1 == 0x9ea9a000ULL && scm_full[1].arg2 == 0x1000);
    assert(scm_full[2].fid == 0xC2000205ULL && scm_full[2].arginfo == 1 && scm_full[2].arg0 == 13);
    assert(zap_region[0x1000] == 1 && zap_region[0x1001] == 2 && zap_region[0x1002] == 3);
    assert(zap_region[0] == 4 && zap_region[1] == 5 && zap_region[2] == 6 && zap_region[0xfff] == 0);
    puts("PASS: FP6 signed ZAP PAS load is opt-in, stage-ordered, and shuts down on failure");
    fp6_map_calls = 0; fp6_mode = fp6_pas_mode = 1; fp6_zap_mode = fp6_smmu_mode = 0; scm_calls = 0;
    fp6_adreno_startup();
    assert(fp6_map_calls == 1 && scm_calls == 2);
    puts("PASS: FP6 Adreno work starts from its dedicated EARLY_BOOT hook");

    /* Patch 0169 snapshots the powered CB0 state without taking ownership.
     * Keep the measured disabled-but-nonzero baseline intact and verify every
     * stream group is read without issuing any MMIO write. */
    memset(fp6_smmu, 0, sizeof(fp6_smmu));
    fp6_smmu[0x20/4] = 0x4c017e18u;
    fp6_smmu[0x24/4] = 0x40000016u;
    fp6_smmu[(0x20000 + 0x00)/4] = 0x2ff5c314u;
    fp6_smmu[(0x20000 + 0x30)/4] = 0x7d0e6f8cu;
    fp6_smmu[(0x20000 + 0x10)/4] = 0x00038065u;
    fp6_smmu[(0x20000 + 0x20)/4] = 0x0fcb6d7bu;
    fp6_smmu[(0x20000 + 0x24)/4] = 0x19b14377u;
    fp6_smmu[(0x20000 + 0x28)/4] = 0xaf8db9f4u;
    fp6_smmu[(0x20000 + 0x2c)/4] = 0xdc20c8e1u;
    fp6_smmu[(0x20000 + 0x38)/4] = 0x079fae8au;
    fp6_smmu[(0x20000 + 0x3c)/4] = 0x8899bf1fu;
    for (unsigned i = 0; i < 24; i++) fp6_smmu[(0xc00 + 4*i)/4] = 0x00020000u;
    fp6_smmu[(0xc00 + 4*7)/4] = 0; /* surfaced as the one anomalous route */
    static uint32_t smmu_snapshot_before[0x40000 / 4];
    memcpy(smmu_snapshot_before, fp6_smmu, sizeof(smmu_snapshot_before));
    all_mmio_writes = 0; output[0] = 0;
    fp6_smmu_cb0_snapshot((vm_offset_t)fp6_smmu, "host-test");
    assert(all_mmio_writes == 0);
    assert(!memcmp(smmu_snapshot_before, fp6_smmu, sizeof(smmu_snapshot_before)));
    assert(strstr(output, "CB0 stage=host-test CBAR=0x00000000 CBA2R=0x00000000 SCTLR=0x2ff5c314"));
    assert(strstr(output, "TTBR0=0x19b143770fcb6d7b TTBR1=0xdc20c8e1af8db9f4"));
    assert(strstr(output, "group=7 SMR=0x00000000 S2CR=0x00000000"));
    puts("PASS: FP6 CB0 stage snapshot reports disabled state without SMMU writes");

    /* Exercise the actual GMU clock path, including the inherited phone state.
     * The earlier inventory tests intentionally leave fp6gmuload disabled. */
    fp6_gmu_clock_model = 1;
    memset(fp6_gpucc, 0, sizeof(fp6_gpucc));
    memset(fp6_gcc_gpu, 0, sizeof(fp6_gcc_gpu));
    fp6_gpucc[0x9094/4] = 1u << 31;
    fp6_gpucc[0x90d4/4] = 0x2001;
    fp6_gpucc[0] = 0x80000005u;
    fp6_gpucc[4/4] = 1;
    fp6_gpucc[0x10/4] = 0x44440024;
    fp6_gpucc[0x14/4] = 0x7555;
    fp6_gpucc[0x18/4] = 0x400; /* correct divider, outputs still disabled */
    fp6_gcc_pll[0] = 0x80000005u;
    fp6_gcc_pll[0x10/4] = 31;
    fp6_gcc_pll[0x14/4] = 0x4000; /* 600 MHz */
    clocks.gpucc = (vm_offset_t)fp6_gpucc;
    clocks.gcc = (vm_offset_t)fp6_gcc_gpu;
    clocks.acquired = 4;
    /* Never touch clocks when inherited CM3 is running. */
    fp6_gmu_regs[0x47000/4] = 0;
    all_mmio_writes = 0;
    assert(!fp6_gmu_clocks_prepare(&clocks) && all_mmio_writes == 0);
    fp6_gmu_regs[0x47000/4] = 1;
    /* Replace cmd-db entry with MX; CX already acknowledged by earlier test. */
    fp6_cmd_db[0x190/4] = 0x6c2e786d;
    fp6_cmd_db[0x1a0/4] = 0x30010;
    fp6_cmd_db[0x1a4/4] = 10;
    fp6_cmd_db[0x210/4] = 64u << 16;
    fp6_cmd_db[0x214/4] = 128u | (192u << 16);
    fp6_cmd_db[0x218/4] = 384u;
    assert(fp6_arc_level((vm_offset_t)fp6_cmd_db, 1, &arc_address, &arc_level));
    assert(arc_level == 3); /* SVS_L1 calibration floor, never LOW_SVS */
    assert(fp6_gmu_clocks_prepare(&clocks));
    assert(fp6_gpucc[0x18/4] == 0x407); /* inherited output enables repaired */
    assert(fp6_gpucc[0x10/4] == 0x44440024 && fp6_gpucc[0x14/4] == 0x7555);
    assert(fp6_gpucc[0x931c/4] == 0x100201 && fp6_gpucc[0x93f0/4] == 0x100505);
    assert(fp6_gcc_votes[0x20/4] == 1 && fp6_gcc_votes[0] == (1u << 15));
    assert(fp6_rsc[(0xd00+0x3c)/4] == 3);
    assert(fp6_gmu_regs[0x47000/4] == 1); /* clock setup never releases CM3 */
    /* Unsupported live rate/divider/FSM cannot be silently retuned. */
    const unsigned bad_off[] = {0x10, 0x10, 0x18, 0x18, 4, 0x14};
    const uint32_t bad_value[] = {0, 0x43, 7, 0x2000407, 0xffffffff, 0xffffffff};
    for (unsigned i = 0; i < sizeof(bad_off)/sizeof(bad_off[0]); i++) {
        unsigned off = bad_off[i]/4;
        uint32_t saved = fp6_gpucc[off]; fp6_gpucc[off] = bad_value[i];
        all_mmio_writes = 0;
        assert(!fp6_gmu_pll700((vm_offset_t)fp6_gpucc) && all_mmio_writes == 0);
        fp6_gpucc[off] = saved;
    }
    /* A stuck root must prevent changing CFG; mapping failure is diagnosed. */
    fp6_root_stuck = 1; fp6_gpucc[0x9318/4] = 1u << 31;
    assert(!fp6_gmu_rcg_set((vm_offset_t)fp6_gpucc, 0x9318, 0x100001));
    assert(fp6_gpucc[0x931c/4] == 0x100201);
    fp6_root_stuck = 0; fp6_gpucc[0x9318/4] = 0;
    fp6_fail_pll_map = 1; output[0] = 0;
    assert(!fp6_gmu_clocks_prepare(&clocks));
    assert(strstr(output, "GCC PLL/vote mapping"));
    fp6_fail_pll_map = 0; fp6_gmu_clock_model = 0;
    puts("PASS: FP6 GMU clock setup, inherited PLL outputs, MX calibration floor and failure gates");
    return 0;
}
'''


if __name__ == '__main__':
    unittest.main()
