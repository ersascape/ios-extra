"""The PM4 builder's load-action clear against Mesa Turnip's A810 streams.

Fixtures (tests/fixtures/turnip-a810-*.rd) are Mesa 6a7d3020a781 Turnip captures made through the freedreno noop
shim with TU_GMEM=622592 TU_DEBUG=sysmem,noubwc,syncdraw (no device data) by tools/fp6-vk-scenes.c: flat, blend,
flatclr (flat cleared to 0.25/0.5/0.75/1), texture, and fill2d (vkCmdFillBuffer, the one 2D-engine solid fill Turnip
emits on the A810)."""
import subprocess
from pathlib import Path
import unittest

from adrenogpu_pm4_common import (BuilderTestCase, Capture, H, OP_COND_REG_EXEC, OP_CP_BLIT, OP_DRAW, OP_EVENT_WRITE7,
                                  SET_BY_PROGRAM, clear_rgba, compare_state, flatten, is_cond_exec,
                                  is_end_resolve_group, pass_params, slice_between, walk_words, words_of)


class GenericClearTests(BuilderTestCase):
    def test_clear_packets_and_state_match_turnip(self):
        # (fixture, packed clear word Turnip put in RB_RESOLVE_CLEAR_COLOR_DW0)
        for name, packed in (('flat', 0xff000000), ('blend', 0xffff0000), ('flatclr', 0xffbf8040)):
            with self.subTest(scene=name):
                cap = Capture('turnip-a810-%s.rd' % name)
                self.assertEqual(cap.pkt4('RB_RESOLVE_CNTL_1')[0], (0, 0x3f003f))
                self.assertEqual([p[0] for k, o, p in cap.trace if k == 'pkt4' and o == 0x88df][0], packed)
                lines = pass_params(cap) + ['clear_mode 1', 'clear_rgba %s' % ' '.join(repr(x) for x in clear_rgba(cap)),
                                            'no_program']
                builder = walk_words(self.scene(name, lines))
                turnip_clear = slice_between(cap.trace, is_cond_exec, is_end_resolve_group)
                builder_clear = slice_between(builder.trace, is_cond_exec, is_end_resolve_group)
                # the whole blit-event clear: conditional-execution header, scissor, clear value, resolve setup,
                # buffer description, CCU_RESOLVE and CCU_END_RESOLVE_GROUP, packet for packet
                self.assertEqual(builder_clear, turnip_clear)
                self.assertEqual(len(turnip_clear), 11)
                equal, bad = compare_state(builder, cap, ignore=SET_BY_PROGRAM)
                self.assertEqual(bad, [])
                self.assertGreaterEqual(equal, 130)

    def test_clear_value_packing(self):
        # Turnip packs RGBA8 clear values with round-to-nearest-even of x * 255; 0.25, 0.5 and 0.75 are
        # 63.75, 127.5 and 191.25 (tie to even) and give 0x40, 0x80, 0xbf as in the flatclr capture.
        cap = Capture('turnip-a810-flatclr.rd')
        for rgba, packed in (([0.25, 0.5, 0.75, 1.0], 0xffbf8040), ([0.0, 0.0, 1.0, 1.0], 0xffff0000)):
            lines = pass_params(cap) + ['clear_mode 1', 'clear_rgba %s' % ' '.join(repr(x) for x in rgba), 'no_program']
            builder = walk_words(self.scene('pack', lines))
            writes = [p[0] for k, o, p in builder.trace if k == 'pkt4' and o == 0x88df]
            self.assertEqual(writes, [packed])

    def test_unsupported_formats_are_refused(self):
        cap = Capture('turnip-a810-flat.rd')
        lines = [l for l in pass_params(cap) if not l.startswith('color.rb_format')]
        for extra in (['color.rb_format 49'],):  # not FMT6_8_8_8_8_UNORM
            with self.assertRaises(RuntimeError):
                self.scene('bad', lines + extra + ['clear_mode 1', 'clear_rgba 0 0 0 1', 'no_program'])


class Clear2dTests(BuilderTestCase):
    def test_solid_fill_matches_turnip_vkCmdFillBuffer(self):
        cap = Capture('turnip-a810-fill2d.rd', sysmem=False)
        turnip = flatten(slice_between(cap.trace, lambda e: e[0] == 'pkt4' and e[1] == H.reg('RB_A2D_PIXEL_CNTL'),
                                       lambda e: e[0] == 'pkt7' and e[1] == OP_CP_BLIT))
        dest = [p for k, o, p in cap.trace if k == 'pkt4' and o == H.reg('RB_A2D_DEST_BUFFER_INFO')][0]
        va = dest[1] | dest[2] << 32
        word = [p for k, o, p in cap.trace if k == 'pkt4' and o == H.reg('RB_A2D_CLEAR_COLOR_DW0')][0][0]
        br = [p for k, o, p in cap.trace if k == 'pkt4' and o == H.reg('GRAS_A2D_DEST_TL')][0][1]
        self.assertEqual(word, 0x40bf80ff)
        dump = Path(self.work.name) / 'fill.bin'
        run = subprocess.run([str(self.exe), 'fill2d', str(dump), '%x' % va, str((br & 0x3fff) + 1), '%x' % word],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        builder = flatten(walk_words(words_of(dump)).trace)
        # every register of the 2D setup, clear value, destination and coordinates, and the CP_BLIT: Turnip's A810 stream
        self.assertEqual(builder, turnip)
        self.assertEqual(len(turnip), 1 + 1 + 1 + 1 + 1 + 4 + 4 + 2 + 1)

    def test_image_destination_has_the_flag_buffer_registers(self):
        # Turnip's r2d_dst for an image: RB_A2D_DEST_BUFFER_INFO (info, base, pitch) then the flag buffer base and
        # pitch at 0x8c20. Taken from the texture capture's buffer-to-image copy; the builder's destination block for
        # the same linear 4x4 RGBA8 image must be the same two packets.
        cap = Capture('turnip-a810-texture.rd', sysmem=False)
        info = H.reg('RB_A2D_DEST_BUFFER_INFO')
        i = next(k for k, e in enumerate(cap.trace) if e[0] == 'pkt4' and e[1] == info)
        turnip = [cap.trace[i], cap.trace[i + 1]]
        self.assertEqual(turnip[1][1], 0x8c20)
        dest = turnip[0][2]
        lines = ['width 4', 'height 4', 'color.va 0x%x' % (dest[1] | dest[2] << 32), 'color.pitch %d' % (dest[3] << 6),
                 'color.layer_bytes 1024', 'color.rb_format %d' % H.field('RB_A2D_DEST_BUFFER_INFO', 'COLOR_FORMAT', dest[0]),
                 'color.swap 0', 'color.tile_mode 0', 'border_color_va 0x100004200', 'clear_mode 2',
                 'clear_rgba 0 0 0 1', 'no_program']
        builder = walk_words(self.scene('img2d', lines))
        j = next(k for k, e in enumerate(builder.trace) if e[0] == 'pkt4' and e[1] == info)
        self.assertEqual(builder.trace[j:j + 2], turnip)

    def test_clear_in_pass_is_bracketed_and_drains(self):
        cap = Capture('turnip-a810-flat.rd')
        lines = pass_params(cap) + ['clear_mode 2', 'clear_rgba 0.25 0.5 0.75 1', 'no_program']
        builder = walk_words(self.scene('pass2d', lines))
        ops = [(e[1], e[2][0] & 0xff if e[0] == 'pkt7' and e[2] else None) for e in builder.trace if e[0] == 'pkt7']
        blit = [i for i, o in enumerate(ops) if o[0] == OP_CP_BLIT]
        draw = [i for i, o in enumerate(ops) if o[0] == OP_DRAW]
        self.assertEqual(len(blit), 1)
        self.assertLess(blit[0], draw[0])
        clean_color, wfi = 0x21, 0x26
        # before the fill: CCU colour clean, then a drain; after it: clean again and a drain, all before the draw
        before = ops[:blit[0]]
        after = ops[blit[0] + 1:draw[0]]
        self.assertIn((OP_EVENT_WRITE7, clean_color), before[-12:])
        self.assertEqual(before[-1][0], wfi)
        self.assertIn((OP_EVENT_WRITE7, clean_color), after)
        self.assertEqual(after[-1][0], wfi)
        # the four clear words are the four bytes, and the 2D registers are the only extra state
        words = [p for k, o, p in builder.trace if k == 'pkt4' and o == H.reg('RB_A2D_CLEAR_COLOR_DW0')][0]
        self.assertEqual(words, (0x40, 0x80, 0xbf, 0xff))

        def a2d(reg, name):
            return name.startswith(('RB_A2D', 'GRAS_A2D', 'SP_A2D', 'TPL1_A2D')) or 0x8c00 <= reg < 0x8c40  # RB_A2D block, incl. 64-bit highs

        equal, bad = compare_state(builder, cap, a2d, SET_BY_PROGRAM)
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
