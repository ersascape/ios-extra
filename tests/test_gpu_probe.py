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
            subprocess.run(['git', 'apply', '--include=bsd/dev/sweet_gpu.c',
                            str(ROOT / 'xnu/patches/0080-sweet-gpu-probe.patch')],
                           cwd=work, check=True)
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
            self.assertIn('PASS: 11 MMIO boundary cases', result.stdout)


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
static char output[8192];

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
    gcc[GPU_CFG_AHB_CBCR / 4] = GPU_BRANCH_ENABLE;
}

int main(void)
{
    reset(); present = 0; sweet_gpu_probe();
    assert(map_calls == 0 && output[0] == 0);
    reset(); mode = 0; sweet_gpu_probe(); assert(map_calls == 0);
    reset(); mode = 2; sweet_gpu_probe(); assert(map_calls == 0);
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
    puts("PASS: 11 MMIO boundary cases");
    return 0;
}
'''


if __name__ == '__main__':
    unittest.main()
