"""Regression coverage for replaying logs from the new repository."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'xnu_cc', Path(__file__).resolve().parents[1] / 'tools/xnu-cc.py')
xnu_cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xnu_cc)


class CompileLogTests(unittest.TestCase):
    def test_repository_paths(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {}, clear=True):
            log = Path(directory) / 'build.log'
            for repo in ('ios-sweet', 'ios-extra'):
                with self.subTest(repo=repo):
                    root = f'/Users/runner/work/{repo}/{repo}/dxb'
                    log.write_text('/Applications/Xcode.app/clang -c '
                                   f'{root}/xnu/bsd/dev/sweet_gpu.c -I{root}/xnu/bsd\n')
                    self.assertEqual(xnu_cc.ci_root(log), root)
                    with patch.object(xnu_cc, 'CI_DXB', xnu_cc.ci_root(log)):
                        self.assertEqual(list(xnu_cc.commands(log)),
                                         [root + '/xnu/bsd/dev/sweet_gpu.c'])

    def test_ambiguous_log_needs_override(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {}, clear=True):
            log = Path(directory) / 'build.log'
            log.write_text(''.join('/Applications/Xcode.app/clang -c '
                                   f'/Users/runner/work/{repo}/{repo}/dxb/xnu/bsd/a.c\n'
                                   for repo in ('ios-sweet', 'ios-extra')))
            with self.assertRaises(ValueError):
                xnu_cc.ci_root(log)
            with patch.dict('os.environ', {'XNU_CI_DXB': '/custom/runner/dxb/'}):
                self.assertEqual(xnu_cc.ci_root(log), '/custom/runner/dxb')


if __name__ == '__main__':
    unittest.main()
