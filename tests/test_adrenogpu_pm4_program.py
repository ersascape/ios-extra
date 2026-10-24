"""The PM4 builder's shader program state against Mesa Turnip's A810 streams (flat and varying scenes; see
tests/test_adrenogpu_pm4_clear.py for how the fixtures were made)."""
import unittest

from adrenogpu_pm4_common import (BuilderTestCase, Capture, H, clear_rgba, compare_state, flatten, pass_params,
                                  program_params, walk_words)

# Registers set by state this builder does not build yet (rasteriser, viewport, scissor, depth, stencil, blend and
# per-draw state), which Turnip has at the draw. Stated as offsets because many have no name in the header.
FIXED_FUNCTION = (
    {0x08086, 0x08087, 0x0808a, 0x0808b, 0x0808c, 0x0808e, 0x0808f, 0x08090, 0x08091, 0x08092}  # GRAS_SU depth/stencil/offset
    | {0x080c0, 0x080c1, 0x08200, 0x08205, 0x08208, 0x08209, 0x0820a, 0x0820b, 0x0820c, 0x08211}  # clip, guardband, SU
    | {0x08237, 0x08240, 0x08241, 0x08270, 0x08271}                                                # MSAA pos, scissors
    | set(range(0x082d0, 0x082d6))                                                                  # viewport transform
    | {0x08804, 0x0880c, 0x0880e, 0x08820, 0x08821, 0x08865, 0x088f4}                               # MRT control, blend
    | set(range(0x0882a, 0x08830)) | set(range(0x08832, 0x08838)) | set(range(0x0883a, 0x08840))
    | set(range(0x08842, 0x08848)) | set(range(0x0884a, 0x08850)) | set(range(0x08852, 0x08858))
    | set(range(0x0885a, 0x08860))                                                                  # MRT 1-7 blend/control
    | set(range(0x08860, 0x08865)) | {0x08871, 0x08878, 0x08879, 0x08880, 0x08887, 0x08888, 0x08889}  # blend const, depth, stencil
    | {0x088b0, 0x088c0}                                                                            # RB viewport z clamp
    | {0x09306, 0x0930e, 0x0930f, 0x09812, 0x09b01, 0x09b12}                                        # rasteriser stream/cull
    | {0x0a00e, 0x0a00f}                                                                            # VFD index/instance offset
    | {0x0a989, 0x0a98d, 0x0aa04, 0x0aa0c}                                                          # SP blend/MRT/alpha test
    | set(range(0x0a997, 0x0a99e)) | {0x0a9aa, 0x0a9ac, 0x0a9ad, 0x0b309})                          # misc static draw state


class ProgramTests(BuilderTestCase):
    def build(self, name):
        cap = Capture('turnip-a810-%s.rd' % name)
        lines = (pass_params(cap) + ['clear_mode 1', 'clear_rgba %s' % ' '.join(repr(x) for x in clear_rgba(cap))] +
                 program_params(cap))
        return cap, walk_words(self.scene('prog-' + name, lines))

    def test_whole_register_state_matches_turnip(self):
        for name in ('flat', 'varying', 'blend', 'flatclr'):
            with self.subTest(scene=name):
                cap, builder = self.build(name)
                equal, bad = compare_state(builder, cap)
                self.assertEqual(bad, [])
                # Everything Turnip has at the draw that the builder does not write is fixed-function state
                # outside the program: the list above, nothing else.
                missing = {r for r in cap.state if r not in builder.state}
                self.assertEqual(sorted(hex(r) for r in missing - FIXED_FUNCTION), [])
                self.assertGreaterEqual(equal, 190)

    def test_program_register_writes_match_turnip_packet_for_packet(self):
        # Turnip's non-binning program groups (config 0, VS 1, HS/DS/GS 3-5, VPC 7, FS 8), in group order, against the
        # builder's program section: the same register writes in the same order, and the same constant-data UBO loads.
        for name in ('flat', 'varying'):
            with self.subTest(scene=name):
                cap, builder = self.build(name)
                turnip = flatten(cap.group_trace([0, 1, 3, 4, 5, 7, 8]))
                # not through draw state here: the builder's stream runs from the program config CRB to the last
                # FS output register write
                trace = builder.trace
                start = next(i for i, e in enumerate(trace) if e[0] == 'pkt7' and e[1] == 0x5c and e[2][0] == H.reg('SP_MODE_CNTL'))
                last = max(i for i, e in enumerate(trace) if e[0] == 'pkt4' and e[1] == H.reg('RB_PS_OUTPUT_MASK'))
                got = flatten(trace[start:last + 1])
                self.assertEqual(got, turnip)
                self.assertGreater(len(got), 80)

    def test_vs_constant_data_ubo_load(self):
        cap, builder = self.build('flat')
        loads = [e for e in builder.trace if e[0] == 'pkt7' and e[1] == 0x32]
        turnip = [e for e in cap.trace if e[0] == 'pkt7' and e[1] == 0x32]
        self.assertEqual(loads, turnip)
        self.assertEqual(len(loads), 1)

    def test_program_misuse_is_refused(self):
        cap = Capture('turnip-a810-flat.rd')
        base = pass_params(cap) + program_params(cap)
        for bad in (['vs.base_va 0x100005681'], ['fs.base_va 0x100006001'], ['fs_double_threadsize 1']):
            with self.subTest(bad=bad):
                with self.assertRaises(RuntimeError):
                    self.scene('bad', base + bad)


if __name__ == '__main__':
    unittest.main()
