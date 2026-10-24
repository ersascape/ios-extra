#!/usr/bin/env python3
"""Replay the register writes of a PM4 stream and report the state a draw sees.

  fp6-pm4-state.py CAPTURE.rd [--regs Fp6A8xxRegs.h] [--json OUT] [--packets] [--sysmem]
  fp6-pm4-state.py --words STREAM.bin ...          (a raw dword stream, no memory behind it)

Used as the oracle for the portable A810 PM4 builder: a Mesa Turnip capture and the builder's
own stream are walked the same way and their state at the draw is compared register by register.

The walk follows CP_INDIRECT_BUFFER and CP_SET_DRAW_STATE groups. Direct writes (type 4,
CP_CONTEXT_REG_BUNCH, CP_NON_CONTEXT_REG_BUNCH) update the state in stream order; the enabled
draw-state groups are applied in group-id order when the draw packet is reached, which is how
the CP resolves them. Opcodes that carry no register state are skipped.
"""
import gzip
import json
import re
import struct
import sys

OP_INDIRECT_BUFFER = 0x3f
OP_SET_DRAW_STATE = 0x43
OP_CONTEXT_REG_BUNCH = 0x5c
OP_NON_CONTEXT_REG_BUNCH = 0x5d
OP_DRAW_INDX_OFFSET = 0x38
OP_EVENT_WRITE7 = 0x46

RD_GPUADDR, RD_BUFFER_CONTENTS, RD_CMDSTREAM_ADDR = 3, 12, 6
DS_MODE_MASK, DS_SYSMEM = 0x70, 1 << 6  # enable-mask bits BINNING (20), GMEM (21), SYSMEM (22) shifted down by 16
DS_DISABLE = 1 << 1  # CP_SET_DRAW_STATE flags: bit 0 ENABLE_ALL_GROUPS, bit 1 DISABLE, bit 2 DISABLE_ALL_GROUPS


def odd(x):
    return bin(x).count('1') & 1 ^ 1


def parse_rd(path):
    data = gzip.open(path).read()
    off, bos, cur, cmd = 0, [], None, []
    while off < len(data):
        kind, size = struct.unpack_from('<II', data, off)
        off += 8
        payload = data[off:off + size]
        off += size
        if kind == RD_GPUADDR:
            lo, sz, hi = struct.unpack_from('<III', payload)
            cur = ((hi << 32) | lo, sz)
        elif kind == RD_BUFFER_CONTENTS:
            bos.append((cur[0], cur[1], struct.unpack('<%dI' % (len(payload) // 4), payload)))
        elif kind == RD_CMDSTREAM_ADDR:
            lo, dwords, hi = struct.unpack_from('<III', payload)
            cmd.append(((hi << 32) | lo, dwords))
    return bos, cmd


class Memory:
    def __init__(self, bos):
        self.bos = bos

    def read(self, va, dwords):
        for base, size, words in self.bos:
            if base <= va < base + size:
                i = (va - base) // 4
                return list(words[i:i + dwords])
        raise KeyError('no buffer at 0x%x' % va)


def reg_names(header):
    names = {}
    if header:
        for m in re.finditer(r'#define A8XX_REG_(\w+?)\s+0x([0-9a-f]+)u\s*$', open(header).read(), re.M):
            if '__' not in m.group(1):
                names.setdefault(int(m.group(2), 16), m.group(1))
    return names


class Walker:
    def __init__(self, mem):
        self.mem = mem
        self.state = {}
        self.groups = {}
        self.draws = []
        self.packets = 0
        self.trace = None  # set to a list to record every packet in stream order (packet-level oracle)
        # None applies every enabled draw-state group, which is what the walker always did. 'sysmem' applies only the
        # groups whose enable mask includes direct rendering (CP_SET_DRAW_STATE bit 22), so a binning-only group (the
        # binning VS) no longer overrides the render-pass state; groups without any mode bit apply always.
        self.render_mode = None

    def run(self, va, dwords):
        self.stream(self.mem.read(va, dwords) if self.mem else va)

    def stream(self, words):
        i = 0
        while i < len(words):
            h = words[i]
            kind = h >> 28
            if kind == 4:
                reg, count = (h >> 8) & 0x3ffff, h & 0x7f
                if h >> 27 & 1 != odd(reg) or h >> 7 & 1 != odd(count):
                    raise ValueError('bad type-4 parity 0x%08x' % h)
                for k in range(count):
                    self.state[reg + k] = words[i + 1 + k]
                if self.trace is not None:
                    self.trace.append(('pkt4', reg, tuple(words[i + 1:i + 1 + count])))
                i += 1 + count
            elif kind == 7:
                op, count = (h >> 16) & 0x7f, h & 0x3fff
                if h >> 23 & 1 != odd(op) or h >> 15 & 1 != odd(count):
                    raise ValueError('bad type-7 parity 0x%08x' % h)
                self.packet7(op, words[i + 1:i + 1 + count])
                i += 1 + count
            elif h == 0:
                i += 1
            else:
                raise ValueError('unexpected dword 0x%08x at %d' % (h, i))
            self.packets += 1

    def packet7(self, op, p):
        if self.trace is not None:
            self.trace.append(('pkt7', op, tuple(p)))
        if op == OP_INDIRECT_BUFFER:
            self.run(p[0] | (p[1] << 32), p[2])
        elif op == OP_SET_DRAW_STATE:
            for k in range(0, len(p), 3):
                head, lo, hi = p[k:k + 3]
                count, flags, gid = head & 0xffff, (head >> 16) & 0xff, head >> 24
                if flags & 4:  # DISABLE_ALL_GROUPS
                    self.groups.clear()
                elif count and not flags & DS_DISABLE:
                    self.groups[gid] = (lo | (hi << 32), count, flags)
                else:
                    self.groups.pop(gid, None)
        elif op == OP_CONTEXT_REG_BUNCH:
            for k in range(0, len(p) - 1, 2):
                self.state[p[k]] = p[k + 1]
        elif op == OP_NON_CONTEXT_REG_BUNCH:
            for k in range(2, len(p) - 1, 2):
                self.state[p[k]] = p[k + 1]
        elif op == OP_DRAW_INDX_OFFSET:
            at_draw = dict(self.state)
            for gid in sorted(self.groups):
                va, count, flags = self.groups[gid]
                if self.render_mode == 'sysmem' and flags & DS_MODE_MASK and not flags & DS_SYSMEM:
                    continue
                sub = Walker(self.mem)
                sub.state = at_draw
                sub.trace = self.trace
                sub.run(va, count)
            self.draws.append((list(p), at_draw))


def main():
    args = sys.argv[1:]
    header = json_out = None
    path = None
    packets = sysmem = False
    while args:
        a = args.pop(0)
        if a == '--regs':
            header = args.pop(0)
        elif a == '--json':
            json_out = args.pop(0)
        elif a == '--packets':
            packets = True
        elif a == '--sysmem':
            sysmem = True
        else:
            path = a
    bos, cmd = parse_rd(path)
    walker = Walker(Memory(bos))
    if sysmem:
        walker.render_mode = 'sysmem'
    if packets:
        walker.trace = []
    walker.run(*cmd[0])
    if packets:
        names = reg_names(header)
        for kind, op, p in walker.trace:
            if kind == 'pkt4':
                print('pkt4 0x%05x %s %s' % (op, names.get(op, '?'), [hex(x) for x in p]))
            else:
                print('pkt7 op=0x%02x %s' % (op, [hex(x) for x in p]))
        return
    if not walker.draws:
        raise SystemExit('no draw packet found')
    names = reg_names(header)
    payload, state = walker.draws[-1]
    print('%d packets, %d draw(s); last draw payload %s, %d registers set' % (
        walker.packets, len(walker.draws), [hex(x) for x in payload], len(state)))
    out = {'draw': payload, 'regs': {str(k): v for k, v in sorted(state.items())}}
    if json_out:
        json.dump(out, open(json_out, 'w'), indent=1)
    else:
        for reg in sorted(state):
            print('0x%05x %-44s 0x%08x' % (reg, names.get(reg, '?'), state[reg]))


if __name__ == '__main__':
    main()
