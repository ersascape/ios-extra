"""The XNU patch that adds the AdrenoGPU cores must match drivers/adrenogpu (the single source)."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AdrenoGpuPatchTests(unittest.TestCase):
    def test_patch_matches_sources(self):
        spec = importlib.util.spec_from_file_location('make_adrenogpu_patch', ROOT / 'tools/make-adrenogpu-patch.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        patch = ROOT / 'xnu/patches/0221-adrenogpu-cores.patch'
        self.assertEqual(patch.read_text(), module.generate(),
                         'run tools/make-adrenogpu-patch.py after changing drivers/adrenogpu')
        for name in module.CORES:
            self.assertIn('+++ b/bsd/dev/' + name, patch.read_text())


if __name__ == '__main__':
    unittest.main()
