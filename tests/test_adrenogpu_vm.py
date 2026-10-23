"""Build and run the AdrenoGPU address-space core (drivers/adrenogpu) under ASan/UBSan on the host."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'drivers' / 'adrenogpu'


class AdrenoGpuVmTests(unittest.TestCase):
    def test_vm_core(self):
        cc = shutil.which('cc')
        if not cc:
            self.skipTest('no host C compiler')
        with tempfile.TemporaryDirectory(prefix='adrenogpu-vm-') as work:
            exe = Path(work) / 'test_vm'
            build = subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                                    '-I', str(DRIVER), str(DRIVER / 'adrenogpu_vm.c'), str(DRIVER / 'test_vm.c'),
                                    '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('PASS: descriptor matches the proven FP6_AS_PTE_PAGE', run.stdout)
            self.assertIn('PASS: a failed map_range leaves nothing mapped', run.stdout)


if __name__ == '__main__':
    unittest.main()
