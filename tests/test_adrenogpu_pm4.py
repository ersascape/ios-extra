"""The AdrenoGPU PM4 builder against Mesa Turnip's A810 stream.

The builder's restore sequence is walked and compared register by register with the state a Turnip capture
(tests/fixtures/turnip-a810-flat.rd, made with the freedreno noop shim, no device data) has at its draw.
"""
import importlib.util
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PM4 = ROOT / 'drivers' / 'adrenogpu' / 'pm4'
FIXTURE = ROOT / 'tests' / 'fixtures' / 'turnip-a810-flat.rd'

# Registers whose value at the draw is set by later pipeline state, not by the restore sequence.
LATER_STATE = {'PC_STEREO_RENDERING_CNTL', 'VFD_STEREO_RENDERING_CNTL', 'SP_PS_CNTL_0', 'SP_UPDATE_CNTL',
               'GRAS_SC_BIN_CNTL', 'RB_CNTL', 'VPC_SO_OVERRIDE'}  # the last three: LRZ feedback and streamout set by pipeline state
BUILDER_ONLY = {'GRAS_LRZ_VIEW_INFO'}  # written by the builder (as SnapMetal does), never by Turnip
# VFD_VERTEX_BUFFER_SIZE[1..31]: Turnip only writes the slots a draw uses.
UNUSED_SLOTS = 'VFD_VERTEX_BUFFER_SIZE'


def load_walker():
    spec = importlib.util.spec_from_file_location('fp6_pm4_state', ROOT / 'tools' / 'fp6-pm4-state.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Pm4BuilderTests(unittest.TestCase):
    def test_restore_matches_turnip(self):
        cc = shutil.which('cc')
        if not cc:
            self.skipTest('no host C compiler')
        with tempfile.TemporaryDirectory(prefix='adrenogpu-pm4-') as work:
            exe, dump = Path(work) / 'test_pm4', Path(work) / 'restore.bin'
            build = subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                                    '-I', str(PM4), str(PM4 / 'adrenogpu_pm4.c'), str(PM4 / 'test_pm4.c'),
                                    '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            # 0x100004200 is where the Turnip capture keeps its border-colour table.
            run = subprocess.run([str(exe), str(dump), '100004200'], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('PASS: GMEM layout equals the one Turnip emitted for 608 KiB', run.stdout)
            self.assertIn('PASS: the A810 sysmem layout does not fit 576 KiB', run.stdout)
            data = dump.read_bytes()
            walker_module = load_walker()
            builder = walker_module.Walker(None)
            builder.stream(list(struct.unpack('<%dI' % (len(data) // 4), data)))
        if not FIXTURE.exists():
            self.skipTest('Turnip fixture missing')
        bos, cmd = walker_module.parse_rd(str(FIXTURE))
        turnip = walker_module.Walker(walker_module.Memory(bos))
        turnip.run(*cmd[0])
        oracle = turnip.draws[-1][1]
        names = {}
        header = (PM4 / 'Fp6A8xxRegs.h').read_text()
        for m in re.finditer(r'#define A8XX_REG_(\w+?)\s+0x([0-9a-f]+)u\s*$', header, re.M):
            if '__' not in m.group(1):
                names.setdefault(int(m.group(2), 16), m.group(1))
        equal, unexpected = 0, []
        for reg, value in sorted(builder.state.items()):
            name = names.get(reg, '?')
            if reg not in oracle:
                # only the unused vertex-buffer size slots may be absent
                if not (name == UNUSED_SLOTS or reg in range(0xa012, 0xa090)):
                    unexpected.append('absent 0x%05x %s' % (reg, name))
            elif oracle[reg] == value:
                equal += 1
            elif name not in LATER_STATE:
                unexpected.append('0x%05x %s builder=0x%x turnip=0x%x' % (reg, name, value, oracle[reg]))
        self.assertEqual(unexpected, [])
        self.assertGreaterEqual(equal, 69)

    def test_pass_matches_turnip_and_drains_before_cleaning(self):
        cc = shutil.which('cc')
        if not cc or not FIXTURE.exists():
            self.skipTest('no host C compiler or fixture')
        header = (PM4 / 'Fp6A8xxRegs.h').read_text()

        def reg(name):
            return int(re.search(r'#define A8XX_REG_%s\s+0x([0-9a-f]+)u' % name, header).group(1), 16)

        def field(name, fld, value):
            shift = int(re.search(r'A8XX_REG_%s__%s__SHIFT\s+(\d+)u' % (name, fld), header).group(1))
            width = int(re.search(r'A8XX_REG_%s__%s__WIDTH\s+(\d+)u' % (name, fld), header).group(1))
            shr = re.search(r'A8XX_REG_%s__%s__SHR\s+(\d+)u' % (name, fld), header)
            return ((value >> shift) & ((1 << width) - 1)) << (int(shr.group(1)) if shr else 0)

        module = load_walker()
        bos, cmd = module.parse_rd(str(FIXTURE))
        turnip = module.Walker(module.Memory(bos))
        turnip.run(*cmd[0])
        payload, state = turnip.draws[-1]
        info = state[reg('RB_MRT_BUF_INFO')]
        base = reg('RB_MRT_BASE')
        border = reg('TPL1_GFX_BORDER_COLOR_BASE')
        scissor = state[reg('GRAS_SC_WINDOW_SCISSOR_BR')]
        args = ['pass', None, str((scissor & 0x3fff) + 1), str(((scissor >> 16) & 0x3fff) + 1),
                '%x' % (state[base] | (state[base + 1] << 32)),
                str(field('RB_MRT_PITCH', 'VALUE', state[reg('RB_MRT_PITCH')])),
                str(field('RB_MRT_ARRAY_PITCH', 'VALUE', state[reg('RB_MRT_ARRAY_PITCH')])),
                str(field('RB_MRT_BUF_INFO', 'COLOR_FORMAT', info)), str(field('RB_MRT_BUF_INFO', 'COLOR_SWAP', info)),
                str(field('RB_MRT_BUF_INFO', 'COLOR_TILE_MODE', info)),
                '%x' % (state[border] | (state[border + 1] << 32))]
        with tempfile.TemporaryDirectory(prefix='adrenogpu-pm4-') as work:
            exe, dump = Path(work) / 'test_pm4', Path(work) / 'pass.bin'
            build = subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                                    '-I', str(PM4), str(PM4 / 'adrenogpu_pm4.c'), str(PM4 / 'test_pm4.c'),
                                    '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            args[1] = str(dump)
            run = subprocess.run([str(exe)] + args, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            data = dump.read_bytes()
        words = list(struct.unpack('<%dI' % (len(data) // 4), data))
        ops = []

        class Logging(module.Walker):
            def packet7(self, op, p):
                ops.append((op, p[0] & 0xff if p else None))
                super().packet7(op, p)

        builder = Logging(None)
        builder.stream(words)
        self.assertEqual(builder.draws[-1][0], payload)
        names = {}
        for m in re.finditer(r'#define A8XX_REG_(\w+?)\s+0x([0-9a-f]+)u\s*$', header, re.M):
            if '__' not in m.group(1):
                names.setdefault(int(m.group(2), 16), m.group(1))
        equal, unexpected = 0, []
        for r, value in sorted(builder.state.items()):
            name = names.get(r, '?')
            if r in range(0xa012, 0xa090):
                continue
            if r not in state:
                if name not in BUILDER_ONLY:
                    unexpected.append('absent 0x%05x %s' % (r, name))
            elif state[r] == value:
                equal += 1
            elif name not in LATER_STATE:
                unexpected.append('0x%05x %s builder=0x%x turnip=0x%x' % (r, name, value, state[r]))
        self.assertEqual(unexpected, [])
        self.assertGreaterEqual(equal, 130)
        # The drain rule: after the draw, a wait-for-idle precedes the first CCU or cache clean.
        after = ops[[i for i, o in enumerate(ops) if o[0] == 0x38][-1] + 1:]
        first_clean = next(i for i, o in enumerate(after) if o[0] == 0x46 and o[1] in (0x20, 0x21, 0x31))
        self.assertTrue(any(o[0] == 0x26 for o in after[:first_clean]), after[:first_clean + 1])


if __name__ == '__main__':
    unittest.main()
