"""Build and run the AdrenoGPU cores (drivers/adrenogpu) under ASan/UBSan on the host."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'drivers' / 'adrenogpu'


class AdrenoGpuCoreTests(unittest.TestCase):
    def run_core(self, sources, test, expected):
        cc = shutil.which('cc')
        if not cc:
            self.skipTest('no host C compiler')
        with tempfile.TemporaryDirectory(prefix='adrenogpu-') as work:
            exe = Path(work) / 'test'
            build = subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                                    '-I', str(DRIVER), *[str(DRIVER / name) for name in sources.split()],
                                    str(DRIVER / test), '-o', str(exe)],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            for line in expected:
                self.assertIn(line, run.stdout)

    def test_vm_core(self):
        self.run_core('adrenogpu_vm.c', 'test_vm.c', [
            'PASS: descriptor matches the proven FP6_AS_PTE_PAGE',
            'PASS: a failed map_range leaves nothing mapped'])

    def test_context_core(self):
        self.run_core('adrenogpu_vm.c adrenogpu_ctx.c', 'test_ctx.c', [
            'PASS: a scattered buffer object is mapped page by page',
            'PASS: a failed mapping leaves nothing behind and can be retried',
            'PASS: fences are ordered and survive 32-bit wrap'])

    def test_submission_queue(self):
        self.run_core('adrenogpu_vm.c adrenogpu_ctx.c adrenogpu_ring.c adrenogpu_sched.c', 'test_sched.c', [
            'PASS: a job that straddles the end of the ring is written and read back intact',
            'PASS: a reset abandons pending jobs, wakes their waiters and marks the fences lost',
            'PASS: the sequence wraps and skips zero'])

    def test_ring_framing(self):
        self.run_core('adrenogpu_ring.c', 'test_ring.c', [
            'PASS: type-7 headers match captured Turnip headers',
            'PASS: submission framing has the sequence the phone ran (36 dwords, 18 packets)'])


if __name__ == '__main__':
    unittest.main()
