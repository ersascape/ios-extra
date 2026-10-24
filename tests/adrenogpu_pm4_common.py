"""Helpers shared by the PM4 builder tests: the register header, the Turnip capture walker, a build of the C test
program, and the readers that turn a Turnip A810 capture into the parameters the builder is given."""
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
FIXTURES = ROOT / 'tests' / 'fixtures'
INVALID = 0xfc  # ir3 regid(63, 0)

OP_EVENT_WRITE7 = 0x46
OP_CP_BLIT = 0x2c
OP_COND_REG_EXEC = 0x47
OP_LOAD_STATE6_GEOM, OP_LOAD_STATE6_FRAG = 0x32, 0x34
OP_SET_DRAW_STATE = 0x43
OP_DRAW = 0x38


def load_walker():
    spec = importlib.util.spec_from_file_location('fp6_pm4_state', ROOT / 'tools' / 'fp6-pm4-state.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Header:
    """Registers and fields of the generated A8XX header."""

    def __init__(self):
        self.text = (PM4 / 'Fp6A8xxRegs.h').read_text()
        self.names = {}
        for m in re.finditer(r'#define A8XX_REG_(\w+?)\s+0x([0-9a-f]+)u\s*$', self.text, re.M):
            if '__' not in m.group(1):
                self.names.setdefault(int(m.group(2), 16), m.group(1))

    def reg(self, name):
        return int(re.search(r'#define A8XX_REG_%s\s+0x([0-9a-f]+)u' % name, self.text).group(1), 16)

    def field(self, reg, fld, value):
        """The input value of a field (before the register's own shift right), from a register value."""
        shift = int(re.search(r'A8XX_REG_%s__%s__SHIFT\s+(\d+)u' % (reg, fld), self.text).group(1))
        width = int(re.search(r'A8XX_REG_%s__%s__WIDTH\s+(\d+)u' % (reg, fld), self.text).group(1))
        shr = re.search(r'A8XX_REG_%s__%s__SHR\s+(\d+)u' % (reg, fld), self.text)
        return ((value >> shift) & ((1 << width) - 1)) << (int(shr.group(1)) if shr else 0)


H = Header()


class Capture:
    """A Turnip capture walked once for the register state at its (last) draw and once packet by packet."""

    def __init__(self, name, sysmem=True):
        self.path = FIXTURES / name
        module = load_walker()
        bos, cmd = module.parse_rd(str(self.path))

        class Recording(module.Walker):
            at = {}

            def packet7(self, op, p):
                if op == OP_DRAW:
                    self.at = dict(self.groups)
                super().packet7(op, p)

        self.module, self.bos = module, bos
        self.walker = Recording(module.Memory(bos))
        self.walker.render_mode = 'sysmem' if sysmem else None
        self.walker.trace = []
        self.walker.run(*cmd[0])
        self.trace = self.walker.trace
        if self.walker.draws:
            self.payload, self.state = self.walker.draws[-1]

    def reg(self, name, i=0):
        return self.state[H.reg(name) + i]

    def fld(self, reg, fld):
        return H.field(reg, fld, self.reg(reg))

    def group_trace(self, gids):
        """The packets of the given draw-state groups, in group-id order, as the draw applies them."""
        out = []
        for gid in sorted(gids):
            va, count, _flags = self.walker.at[gid]
            sub = self.module.Walker(self.module.Memory(self.bos))
            sub.trace = out
            sub.run(va, count)
        return out

    def pkt4(self, name):
        """Every type-4 packet writing the register, in stream order."""
        off = H.reg(name)
        return [p for kind, o, p in self.trace if kind == 'pkt4' and o == off]


def build_test_program(work):
    cc = shutil.which('cc')
    if not cc:
        return None
    exe = Path(work) / 'test_pm4'
    build = subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                            '-I', str(PM4), str(PM4 / 'adrenogpu_pm4.c'), str(PM4 / 'test_pm4.c'), '-o', str(exe)],
                           capture_output=True, text=True)
    if build.returncode:
        raise RuntimeError(build.stderr)
    return exe


def words_of(path):
    data = Path(path).read_bytes()
    return list(struct.unpack('<%dI' % (len(data) // 4), data))


def pass_params(cap):
    """Pass description lines from a capture: size, colour target, border colour table."""
    info = cap.reg('RB_MRT_BUF_INFO')
    scissor = cap.reg('GRAS_SC_WINDOW_SCISSOR_BR')
    base = H.reg('RB_MRT_BASE')
    border = H.reg('TPL1_GFX_BORDER_COLOR_BASE')
    return ['width %d' % ((scissor & 0x3fff) + 1), 'height %d' % (((scissor >> 16) & 0x3fff) + 1),
            'color.va 0x%x' % (cap.state[base] | (cap.state[base + 1] << 32)),
            'color.pitch %d' % H.field('RB_MRT_PITCH', 'VALUE', cap.reg('RB_MRT_PITCH')),
            'color.layer_bytes %d' % H.field('RB_MRT_ARRAY_PITCH', 'VALUE', cap.reg('RB_MRT_ARRAY_PITCH')),
            'color.rb_format %d' % H.field('RB_MRT_BUF_INFO', 'COLOR_FORMAT', info),
            'color.swap %d' % H.field('RB_MRT_BUF_INFO', 'COLOR_SWAP', info),
            'color.tile_mode %d' % H.field('RB_MRT_BUF_INFO', 'COLOR_TILE_MODE', info),
            'border_color_va 0x%x' % (cap.state[border] | (cap.state[border + 1] << 32)),
            'draw %d %d %d' % (cap.payload[0] & 0x3f, cap.payload[1], cap.payload[2])]


def xs_params(cap, stage, load_state_op):
    """The fields of one stage the compiler hands over, read back out of the capture's registers."""
    p = 'vs' if stage == 'VS' else 'fs'
    cntl0 = '%s_CNTL_0' % ('SP_VS' if stage == 'VS' else 'SP_PS')
    cfg = 'SP_VS_CONFIG' if stage == 'VS' else 'SP_PS_CONFIG'
    ccfg = 'SP_VS_CONST_CONFIG' if stage == 'VS' else 'SP_PS_CONST_CONFIG'
    pre = 'SP_VS' if stage == 'VS' else 'SP_PS'
    sz = 'SP_VS_INSTR_SIZE' if stage == 'VS' else 'SP_PS_INSTR_SIZE'
    base = cap.reg(pre + '_BASE') | (cap.reg(pre + '_BASE', 1) << 32)
    out = ['%s.base_va 0x%x' % (p, base), '%s.instrlen %d' % (p, cap.reg(sz)),
           '%s.constlen %d' % (p, cap.fld(ccfg, 'CONSTLEN')),
           '%s.half_reg_footprint %d' % (p, cap.fld(cntl0, 'HALFREGFOOTPRINT')),
           '%s.full_reg_footprint %d' % (p, cap.fld(cntl0, 'FULLREGFOOTPRINT')),
           '%s.branchstack %d' % (p, cap.fld(cntl0, 'BRANCHSTACK')),
           '%s.mergedregs %d' % (p, cap.fld(cntl0, 'MERGEDREGS')),
           '%s.early_preamble %d' % (p, cap.fld(cntl0, 'EARLYPREAMBLE')),
           '%s.pvtmem_per_fiber_size %d' % (p, cap.fld(pre + '_PVT_MEM_PARAM', 'MEMSIZEPERITEM')),
           '%s.pvtmem_va 0x%x' % (p, cap.reg(pre + '_PVT_MEM_BASE') | (cap.reg(pre + '_PVT_MEM_BASE', 1) << 32)),
           '%s.pvtmem_per_sp_size %d' % (p, cap.fld(pre + '_PVT_MEM_SIZE', 'TOTALPVTMEMSIZE')),
           '%s.pvtmem_per_wave %d' % (p, cap.fld(pre + '_PVT_MEM_SIZE', 'PERWAVEMEMLAYOUT')),
           '%s.bindless_tex %d' % (p, cap.fld(cfg, 'BINDLESS_TEX')),
           '%s.bindless_samp %d' % (p, cap.fld(cfg, 'BINDLESS_SAMP')),
           '%s.bindless_uav %d' % (p, cap.fld(cfg, 'BINDLESS_UAV')),
           '%s.bindless_ubo %d' % (p, cap.fld(cfg, 'BINDLESS_UBO')),
           '%s.num_samp %d' % (p, cap.fld(cfg, 'NSAMP')),
           '%s.num_uav %d' % (p, cap.fld(cfg, 'NUAV'))]
    ubo = [pk for kind, op, pk in cap.trace if kind == 'pkt7' and op == load_state_op and len(pk) == 5]
    assert len(ubo) <= 1
    if ubo:
        head, _, _, lo, hi = ubo[0]
        va = lo | ((hi & 0x1ffff) << 32)
        out += ['%s.const_ubo_idx %d' % (p, head & 0x3fff), '%s.const_data_offset %d' % (p, va - base),
                '%s.const_data_size %d' % (p, (hi >> 17) * 16)]
    return out


def program_params(cap):
    out = xs_params(cap, 'VS', OP_LOAD_STATE6_GEOM) + xs_params(cap, 'FS', OP_LOAD_STATE6_FRAG)
    cnt1 = H.reg('VFD_CNTL_1')
    c1 = cap.state[cnt1]
    out += ['vs_vertexid_regid %d' % (c1 & 0xff), 'vs_instanceid_regid %d' % (c1 >> 8 & 0xff),
            'vs_primid_regid %d' % (c1 >> 16 & 0xff), 'vs_viewid_regid %d' % (c1 >> 24 & 0xff)]
    attr_in = cap.fld('VFD_CNTL_0', 'DECODE_CNT')
    out.append('vs_attr_in %d' % attr_in)
    for i in range(attr_in):
        v = cap.reg('VFD_DEST_CNTL_INSTR', i)
        out.append('vs_attr %d %d %d' % (i, v >> 4 & 0xff, v & 0xf))
    # VS outputs, in the order SP_VS_OUTPUT_REG lists them; the one at POSITIONLOC with all four components is gl_Position
    n_out = cap.fld('SP_VS_OUTPUT_CNTL', 'OUT')
    position_loc = cap.fld('VPC_VS_CNTL', 'POSITIONLOC')
    total_in = cap.fld('VPC_PS_CNTL', 'NUMNONPOSVAR')
    interp = cap.state.get(H.reg('VPC_VARYING_INTERP_MODE_MODE'), 0)
    varyings, position = [], None
    for i in range(n_out):
        word = cap.reg('SP_VS_OUTPUT_REG', i // 2) >> (16 * (i % 2))
        regid, compmask = word & 0xff, word >> 8 & 0xf
        loc = cap.reg('SP_VS_VPC_DEST_REG', i // 4) >> (8 * (i % 4)) & 0xff
        if loc == position_loc and compmask == 0xf and i == n_out - 1:
            position = regid
        else:
            flat = 1 if (interp >> (loc * 2)) & 3 == 1 else 0
            varyings.append((loc, compmask, flat, regid))
    out.append('vs_position_regid %d' % position)
    for i, (loc, compmask, flat, regid) in enumerate(varyings):
        out.append('fs_varying %d %d %d %d %d' % (i, loc, compmask, flat, regid))
    out.append('fs_total_in %d' % total_in)
    out += ['fs_double_threadsize %d' % cap.fld('SP_PS_CNTL_0', 'THREADSIZE'),
            'fs_need_full_quad %d' % cap.fld('SP_PS_CNTL_0', 'LODPIXMASK'),
            'fs_need_pixlod %d' % cap.fld('SP_PS_CNTL_0', 'PIXLODENABLE'),
            'fs_sample_shading %d' % cap.fld('RB_PS_SAMPLEFREQ_CNTL', 'PER_SAMP_MODE'),
            'fs_post_depth_coverage %d' % cap.fld('RB_PS_INPUT_CNTL', 'POSTDEPTHCOVERAGE'),
            'fs_frag_face %d' % cap.fld('RB_PS_INPUT_CNTL', 'FACENESS'),
            'fs_face_regid %d' % cap.fld('SP_REG_PROG_ID_0', 'FACEREGID'),
            'fs_sampleid_regid %d' % cap.fld('SP_REG_PROG_ID_0', 'SAMPLEID'),
            'fs_samplemask_in_regid %d' % cap.fld('SP_REG_PROG_ID_0', 'SAMPLEMASK'),
            'fs_shading_rate_regid %d' % cap.fld('SP_REG_PROG_ID_3', 'FOVEATIONQUALITYREGID'),
            'fs_coord_regid %d' % cap.fld('SP_REG_PROG_ID_2', 'XYCOORDREGID'),
            'fs_fragcoord_compmask %d' % cap.fld('RB_INTERP_CNTL', 'COORD_MASK')]
    ij = [cap.fld('SP_REG_PROG_ID_1', 'IJ_PERSP_PIXEL'), cap.fld('SP_REG_PROG_ID_2', 'IJ_PERSP_SAMPLE'),
          cap.fld('SP_REG_PROG_ID_1', 'IJ_PERSP_CENTROID'), cap.fld('SP_REG_PROG_ID_0', 'CENTERRHW'),
          cap.fld('SP_REG_PROG_ID_1', 'IJ_LINEAR_PIXEL'), cap.fld('SP_REG_PROG_ID_1', 'IJ_LINEAR_CENTROID'),
          cap.fld('SP_REG_PROG_ID_2', 'IJ_LINEAR_SAMPLE')]
    out.append('fs_ij_regid ' + ' '.join(str(x) for x in ij))
    aliased = cap.reg('SP_PS_OUTPUT_CONST_MASK')
    mask = cap.reg('SP_PS_OUTPUT_MASK')
    for rt in range(8):
        if mask >> (4 * rt) & 0xf:
            word = cap.reg('SP_PS_OUTPUT_REG', rt)
            out.append('fs_color %d %d %d' % (rt, word & 0xff, word >> 8 & 1))
    out += ['fs_aliased_components %d' % aliased,
            'fs_depth_regid %d' % cap.fld('SP_PS_OUTPUT_CNTL', 'DEPTH_REGID'),
            'fs_samplemask_regid %d' % cap.fld('SP_PS_OUTPUT_CNTL', 'SAMPMASK_REGID'),
            'fs_stencilref_regid %d' % cap.fld('SP_PS_OUTPUT_CNTL', 'STENCILREF_REGID'),
            'fs_dual_src_blend %d' % cap.fld('SP_PS_OUTPUT_CNTL', 'DUAL_COLOR_IN_ENABLE')]
    return out


def clear_rgba(cap):
    """The clear colour a capture's blit-event clear used, as floats that round back to the same bytes."""
    packed = [p[0] for kind, o, p in cap.trace if kind == 'pkt4' and o == 0x88df][0]
    return [((packed >> (8 * i)) & 0xff) / 255.0 for i in range(4)]


def run_scene(exe, work, name, lines):
    params = Path(work) / (name + '.params')
    dump = Path(work) / (name + '.bin')
    params.write_text('\n'.join(lines) + '\n')
    run = subprocess.run([str(exe), 'scene', str(dump), str(params)], capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError(run.stdout + run.stderr)
    return words_of(dump)


def walk_words(words, trace=True):
    module = load_walker()
    w = module.Walker(None)
    if trace:
        w.trace = []
    w.stream(words)
    return w


def flatten(trace):
    """A packet trace as the ordered register writes it makes, with other packets kept whole."""
    out = []
    for kind, op, p in trace:
        if kind == 'pkt4':
            out += [('reg', op + k, v) for k, v in enumerate(p)]
        elif op == 0x5c:
            out += [('reg', p[k], p[k + 1]) for k in range(0, len(p) - 1, 2)]
        elif op == 0x5d:
            out += [('reg', p[k], p[k + 1]) for k in range(2, len(p) - 1, 2)]
        else:
            out.append(('pkt7', op, tuple(p)))
    return out


# Registers whose value at the draw comes from state outside the program: LRZ feedback mode (GRAS_SC_BIN_CNTL,
# RB_CNTL), stream-out override (VPC_SO_OVERRIDE), and the descriptor-set group that finally zeroes SP_UPDATE_CNTL.
OUTSIDE_PROGRAM = {'GRAS_SC_BIN_CNTL', 'RB_CNTL', 'VPC_SO_OVERRIDE', 'SP_UPDATE_CNTL'}
BUILDER_ONLY = {'GRAS_LRZ_VIEW_INFO'}  # written by the builder (as SnapMetal does), never by Turnip


# Values the restore sequence zeroes and only the shader program sets (tests that emit no program tolerate them).
SET_BY_PROGRAM = {'PC_STEREO_RENDERING_CNTL', 'VFD_STEREO_RENDERING_CNTL', 'SP_PS_CNTL_0'}


def compare_state(builder, cap, allow_extra=lambda reg, name: False, ignore=()):
    """Registers the builder wrote that differ from Turnip's at the draw, or that Turnip never had; and the count of equal."""
    equal, bad = 0, []
    for reg, value in sorted(builder.state.items()):
        name = H.names.get(reg, '?')
        if 0xa012 <= reg < 0xa090:  # VFD_VERTEX_BUFFER_SIZE slots: Turnip only writes the ones a draw uses
            continue
        if reg not in cap.state:
            if name not in BUILDER_ONLY and not allow_extra(reg, name):
                bad.append('absent 0x%05x %s' % (reg, name))
        elif cap.state[reg] == value:
            equal += 1
        elif name not in OUTSIDE_PROGRAM and name not in ignore:
            bad.append('0x%05x %s builder=0x%x turnip=0x%x' % (reg, name, value, cap.state[reg]))
    return equal, bad


class BuilderTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory(prefix='adrenogpu-pm4-')
        cls.exe = build_test_program(cls.work.name) if shutil.which('cc') else None

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def setUp(self):
        if not self.exe:
            self.skipTest('no host C compiler')

    def scene(self, name, lines):
        return run_scene(self.exe, self.work.name, name, lines)


def slice_between(trace, start, end):
    """Trace entries from the first one satisfying start through the next satisfying end, inclusive."""
    i = next(k for k, e in enumerate(trace) if start(e))
    j = next(k for k in range(i, len(trace)) if end(trace[k]))
    return trace[i:j + 1]


def is_cond_exec(e):
    return e[0] == 'pkt7' and e[1] == OP_COND_REG_EXEC and e[2][0] == 0x3c000000


def is_end_resolve_group(e):
    return e[0] == 'pkt7' and e[1] == OP_EVENT_WRITE7 and e[2][0] & 0xff == 0x1f
