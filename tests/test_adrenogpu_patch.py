"""The XNU patch that adds the AdrenoGPU cores must match drivers/adrenogpu (the single source)."""
import importlib.util
import re
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

    def load(self):
        spec = importlib.util.spec_from_file_location('make_adrenogpu_patch', ROOT / 'tools/make-adrenogpu-patch.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_device_core_patch_matches_sources(self):
        module = self.load()
        patch = (ROOT / 'xnu/patches/0224-adrenogpu-device-core.patch').read_text()
        self.assertEqual(patch, module.generate_dev(), 'run tools/make-adrenogpu-patch.py --all')
        for name in module.DEV_CORE:
            self.assertIn('+++ b/bsd/dev/' + name, patch)
        self.assertIn('+bsd/dev/adrenogpu_dev.c', patch)

    def test_iokit_shell_patch_matches_sources(self):
        module = self.load()
        patch = (ROOT / 'xnu/patches/0225-adrenogpu-iokit-shell.patch').read_text()
        self.assertEqual(patch, module.generate_shell(), 'run tools/make-adrenogpu-patch.py --all')
        self.assertIn('+++ b/iokit/Kernel/arm/AdrenoGPU.cpp', patch)
        self.assertIn('+iokit/Kernel/arm/AdrenoGPU.cpp', patch)

    def test_shell_adds_no_boot_behaviour(self):
        """No personality matches the class and nothing in the patch series calls the entry point."""
        source = (ROOT / 'drivers/adrenogpu/AdrenoGPU.cpp').read_text()
        self.assertIn('PE_parse_boot_argn("adrenogpu"', source)
        for patch in sorted((ROOT / 'xnu/patches').glob('*.patch')):
            text = patch.read_text(errors='replace')
            if patch.name.startswith('0225-'):
                continue
            self.assertNotIn('adrenogpu_iokit_start', text, patch.name)
            self.assertIsNone(re.search(r"'IOClass'\s*=\s*AdrenoGPU", text), patch.name)


if __name__ == '__main__':
    unittest.main()
