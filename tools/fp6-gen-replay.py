#!/usr/bin/env python3
"""Turn Mesa freedreno `.rd` captures into the C data header used by the FP6
address-space replay probe.

Unlike fp6-gen-compute.py this does not relocate anything. The probe builds a
TTBR0 address space that maps every captured buffer at the exact IOVA Mesa
used, so the command stream can be replayed unchanged through a
CP_INDIRECT_BUFFER. Pages are stored sparsely as (dword index, value) pairs;
zero pages carry no data.

  fp6-gen-replay.py OUT.h NAME:CAPTURE.rd:CHECK[:inject=KEY+KEY...] [...]

inject=KEYS (ccu_clean, ccu_inv, cache_clean, cache_inv, wfi) inserts those cache events before the
draw packet, for A/B tests of which flush the hardware needs.

CHECK is `add5` (computerator buf-init: every element of the UAV buffer grew by
5) or `color` (a Vulkan draw: count RGBA8 words equal to 0xff4080ff in the
capture's zero-initialised buffers). `grid=REF.txt` is a tools/fp6-vk-scenes scene: the
result buffer is the one BO filled with SENTINEL, and REF.txt holds the 16x16
`grid16:` line the same scene printed under lavapipe.
"""
import gzip
import re
import struct
import sys

RD_GPUADDR, RD_BUFFER_CONTENTS, RD_CMDSTREAM_ADDR, RD_CHIP_ID = 3, 12, 6, 14
CHECK = {'add5': 0, 'color': 1, 'scanout': 2, 'grid': 3}
SENTINEL = 0xa5a5a5a5  # fp6-vk-scenes pre-fills its result buffer with this
PAGE = 4096
SMALL_BO = 0x200000  # map every page of BOs up to this size; otherwise sparse
SCANOUT_MIN = 0x800000  # a zero BO at least this big is the scanout framebuffer


def parse(path):
    data = gzip.open(path).read()
    off, bos, cur, cmd, chip = 0, [], None, [], None
    while off < len(data):
        kind, size = struct.unpack_from('<II', data, off)
        off += 8
        payload = data[off:off + size]
        off += size
        if kind == RD_GPUADDR:
            lo, sz, hi = struct.unpack_from('<III', payload)
            cur = ((hi << 32) | lo, sz)
        elif kind == RD_BUFFER_CONTENTS:
            bos.append((cur[0], cur[1], payload))
        elif kind == RD_CMDSTREAM_ADDR:
            lo, dwords, hi = struct.unpack_from('<III', payload)
            cmd.append(((hi << 32) | lo, dwords))
        elif kind == RD_CHIP_ID:
            chip = struct.unpack_from('<I', payload)[0]
    return bos, cmd, chip


def words(blob):
    return list(struct.unpack('<%dI' % (len(blob) // 4), blob))


def packet_ends(stream):
    """Dword offsets where each top-level packet ends (bisection points)."""
    ends, i = [], 0
    while i < len(stream):
        header = stream[i]
        kind = header >> 28
        if kind == 7:
            i += 1 + (header & 0x7fff)
        elif kind == 4:
            i += 1 + (header & 0x7f)
        else:
            raise SystemExit('unexpected packet 0x%08x at dword %d' % (header, i))
        ends.append(i)
    if i != len(stream):
        raise SystemExit('packet walk overran the stream: %d != %d' % (i, len(stream)))
    return ends


def cbd_payloads(bos):
    """GPU addresses of every CP_THREAD_CONTROL payload that sets CONCURRENT_BIN_DISABLE.

    Turnip patches these at submit time (plain BR when concurrent binning is on).
    The probe can clear the bit to test whether the disable itself hangs the CP.
    """
    out = []
    for base, size, blob in bos:
        w = words(blob)
        for i in range(len(w) - 1):
            if w[i] == 0x70970001 and w[i + 1] & (1 << 27) and (w[i + 1] & 3) and \
                    not w[i + 1] & ~(0x3 | (1 << 27) | (1 << 31)):
                out.append(base + 4 * (i + 1))
    return out


INJECT = {  # CP_EVENT_WRITE7 events (adreno_pm4.xml) and wait-for-idle, as Turnip's flushall emits them
    'ccu_clean': [('event', 0x21), ('event', 0x20)],
    'ccu_inv': [('event', 0x19), ('event', 0x18)],
    'cache_clean': [('event', 0x31)],
    'cache_inv': [('event', 0x33)],
    'wfi': [('wfi', 0)],
}


def pkt7(op, count):
    def odd(x):
        return bin(x).count('1') & 1 ^ 1
    return 0x70000000 | count | (odd(count) << 15) | (op << 16) | (odd(op) << 23)


def inject_words(keys):
    words = []
    for key in keys:
        for kind, arg in INJECT[key]:
            if kind == 'event':
                words += [pkt7(0x46, 1), arg]
            else:
                words += [pkt7(0x26, 0)]
    return words


def inject_before_draw(bos, cmd_va, cmd_dwords, keys):
    """Insert packets before CP_DRAW_INDX_OFFSET and grow the CP_INDIRECT_BUFFER that runs that stream."""
    extra = inject_words(keys)
    draws = []
    for index, (base, size, blob) in enumerate(bos):
        w = words(blob)
        for i, h in enumerate(w):
            if h >> 28 == 7 and (h >> 16) & 0x7f == 0x38 and (h & 0x3fff) in (3, 7):
                draws.append((index, base, i))
    if len(draws) != 1:
        raise SystemExit('inject: expected one draw packet, found %d' % len(draws))
    bo_index, bo_base, at = draws[0]
    base, size, blob = bos[bo_index]
    w = words(blob)
    if w[-len(extra):] != [0] * len(extra):
        raise SystemExit('inject: no room at the end of the draw stream buffer')
    w = w[:at] + extra + w[at:len(w) - len(extra)]
    bos[bo_index] = (base, size, struct.pack('<%dI' % len(w), *w))
    # The stream that calls it: its CP_INDIRECT_BUFFER covers the draw's address.
    draw_va = bo_base + 4 * at
    owner = next((i for i, (b, s, bl) in enumerate(bos) if b <= cmd_va < b + s))
    ob, osz, oblob = bos[owner]
    ow = words(oblob)
    start = (cmd_va - ob) // 4
    i = start
    patched = 0
    while i < start + cmd_dwords:
        h = ow[i]
        count = h & 0x3fff if h >> 28 == 7 else (h & 0x7f)
        if h >> 28 == 7 and (h >> 16) & 0x7f == 0x3f and count == 3:
            lo, hi, ibsz = ow[i + 1], ow[i + 2], ow[i + 3]
            va = lo | (hi << 32)
            if va <= draw_va < va + 4 * (ibsz & 0xfffff):
                ow[i + 3] = (ibsz & ~0xfffff) | ((ibsz & 0xfffff) + len(extra))
                patched += 1
        i += 1 + count
    if patched != 1:
        raise SystemExit('inject: expected one CP_INDIRECT_BUFFER covering the draw, found %d' % patched)
    bos[owner] = (ob, osz, struct.pack('<%dI' % len(ow), *ow))


def build(path, check, grid=None, inject=()):
    bos, cmd, chip = parse(path)
    if chip != 0x44010000:
        raise SystemExit('%s is not an A810 capture: chip 0x%x' % (path, chip or 0))
    if not 1 <= len(cmd) <= 2:
        raise SystemExit('%s: expected one or two command streams, found %d' % (path, len(cmd)))
    cmd_va, cmd_dwords = cmd[0]
    if inject:
        inject_before_draw(bos, cmd_va, cmd_dwords, inject)
    ib2_va, ib2_dwords = cmd[1] if len(cmd) == 2 else (0, 0)
    scanout = None
    if check == 'scanout':
        big = [(b, sz) for b, sz, bl in bos if sz >= SCANOUT_MIN and not any(bl)]
        if len(big) != 1:
            raise SystemExit('%s: expected exactly one zero scanout BO, found %d' % (path, len(big)))
        scanout = big[0]
    result_bo = None
    if check == 'grid':
        found = [(b, sz) for b, sz, bl in bos if sz and all(x == SENTINEL for x in words(bl))]
        if len(found) != 1:
            raise SystemExit('%s: expected exactly one sentinel result BO, found %d' % (path, len(found)))
        result_bo = found[0]
    pages, zero_bo_pages = {}, set()
    for base, size, blob in bos:
        if scanout and base == scanout[0]:
            continue  # backed by the real framebuffer on the device
        w = words(blob)
        if result_bo and base == result_bo[0]:
            w = [0] * len(w)  # the render overwrites every texel; do not store the sentinel
        for p in range(0, size, PAGE):
            chunk = w[p // 4:(p + PAGE) // 4]
            nz = [(i, v) for i, v in enumerate(chunk) if v]
            keep = size <= SMALL_BO or nz
            if keep:
                pages[base + p] = nz
                if not any(w):
                    zero_bo_pages.add(base + p)
    # Sparse (large) BOs also need the pages the stream names as pointers.
    stream_bo = next((b, s, bl) for b, s, bl in bos if b <= cmd_va < b + s)
    if ib2_va:
        stream2 = next((b, s, bl) for b, s, bl in bos if b <= ib2_va < b + s)
        sw2 = words(stream2[2][ib2_va - stream2[0]:ib2_va - stream2[0] + ib2_dwords * 4])
    else:
        sw2 = []
    sw = words(stream_bo[2][cmd_va - stream_bo[0]:cmd_va - stream_bo[0] + cmd_dwords * 4])
    for stream in (sw, sw2):
        for i, v in enumerate(stream[:-2]):
            for base, size, _ in bos:
                if scanout and base == scanout[0]:
                    continue
                if base <= v < base + size and (stream[i + 1] == 0 or (
                        i and stream[i - 1] < 0x10000 and stream[i + 1] < 0x10000 and stream[i + 2] == 0)):
                    pages.setdefault(base + ((v - base) // PAGE) * PAGE, [])
    if scanout:
        for va in [v for v in pages if scanout[0] <= v < scanout[0] + scanout[1]]:
            del pages[va]
    result = {'pages': pages, 'ib_va': cmd_va, 'ib_dwords': cmd_dwords, 'steps': packet_ends(sw), 'cbd': cbd_payloads(bos),
              'ib2_va': ib2_va, 'ib2_dwords': ib2_dwords,
              'scanout_va': scanout[0] if scanout else 0, 'scanout_bytes': scanout[1] if scanout else 0,
              'check': check, 'check_va': 0, 'elements': 0, 'init': []}
    if check == 'grid':
        result['check_va'], result['elements'] = result_bo[0], len(grid)
        result['init'] = grid
    if check == 'add5':
        # The UAV descriptor (TYPE=TEX_BUFFER, nonzero count) names the data buffer.
        for base, size, blob in bos:
            w = words(blob)
            for i in range(0, len(w) - 4, 4):
                if (w[i + 1] >> 17) & 7 == 4 and w[i + 2] and w[i + 3] and w[i] and not w[i + 4]:
                    va = w[i] | ((w[i + 1] & 0x1ffff) << 32)
                    for b2, s2, bl2 in bos:
                        if b2 <= va < b2 + s2:
                            n = w[i + 2] & 0x7fff
                            result['check_va'], result['elements'] = va, n
                            result['init'] = words(bl2[va - b2:va - b2 + n * 4])
                            pages.setdefault(b2 + ((va - b2) // PAGE) * PAGE, [])
        if not result['elements']:
            raise SystemExit('%s: no UAV descriptor found' % path)
    return result


def emit(name, values, kind='uint32_t', per_line=8):
    if not values:
        return None
    suffix = {'uint32_t': 'u', 'uint64_t': 'ull'}.get(kind, '')
    lines = ['static const %s %s[%d] = {' % (kind, name, len(values))]
    for i in range(0, len(values), per_line):
        lines.append('\t' + ', '.join('0x%x%s' % (v, suffix) for v in values[i:i + per_line]) + ',')
    lines.append('};')
    return '\n'.join(lines)


def main():
    if len(sys.argv) < 3:
        raise SystemExit('usage: fp6-gen-replay.py OUT.h NAME:CAPTURE.rd:CHECK ...')
    out_path, specs = sys.argv[1], sys.argv[2:]
    out = ['/* Generated by tools/fp6-gen-replay.py from Mesa freedreno A810 captures.',
           ' * Do not edit; regenerate. Each capture is replayed at its original IOVAs',
           ' * through a TTBR0 address space; pages hold sparse (index, value) pairs. */',
           '#ifndef FP6_GPU_REPLAY_DATA_H',
           '#define FP6_GPU_REPLAY_DATA_H',
           '#define FP6_REPLAY_CHECK_ADD5  0u',
           '#define FP6_REPLAY_CHECK_COLOR 1u',
           '#define FP6_REPLAY_CHECK_SCANOUT 2u',
           '#define FP6_REPLAY_CHECK_GRID 3u',
           'struct fp6_replay_page {',
           '\tuint64_t va;',
           '\tconst uint32_t *pairs; /* (dword index, value) pairs; NULL for a zero page */',
           '\tunsigned npairs;',
           '};',
           'struct fp6_replay {',
           '\tconst char *name;',
           '\tconst struct fp6_replay_page *pages;',
           '\tunsigned npages;',
           '\tuint64_t ib_va;',
           '\tunsigned ib_dwords;',
           '\tunsigned check;',
           '\tuint64_t check_va;',
           '\tunsigned elements;',
           '\tconst uint32_t *init;',
           '\tconst uint16_t *steps; /* top-level packet end offsets, for prefix bisection */',
           '\tunsigned nsteps;',
           '\tconst uint64_t *cbd; /* CP_THREAD_CONTROL payload addresses with CONCURRENT_BIN_DISABLE */',
           '\tunsigned ncbd;',
           '\tuint64_t ib2_va; /* optional second command stream (0 = none) */',
           '\tunsigned ib2_dwords;',
           '\tuint64_t scanout_va; /* BO the device backs with the real framebuffer (0 = none) */',
           '\tunsigned scanout_bytes;',
           '\tunsigned fbw, fbh, tri_x, tri_y, tri_size;',
           '};']
    rows, summary = [], []
    for spec in specs:
        fields = spec.split(':')
        name, path, check = fields[:3]
        inject = ()
        for extra in fields[3:]:
            if not extra.startswith('inject='):
                raise SystemExit('bad spec option %r' % extra)
            inject = tuple(extra.split('=', 1)[1].split('+'))
            if any(k not in INJECT for k in inject):
                raise SystemExit('unknown inject key in %r (have %s)' % (extra, ', '.join(sorted(INJECT))))
        geometry = (0, 0, 0, 0, 0)
        if check.startswith('scanout='):
            geometry = tuple(int(v) for v in check.split('=', 1)[1].split(','))
            if len(geometry) != 5:
                raise SystemExit('scanout needs FBW,FBH,X,Y,SIZE')
            check = 'scanout'
        if check.split('=', 1)[0] not in CHECK or not re.fullmatch(r'[a-z0-9_]+', name):
            raise SystemExit('bad spec %r' % spec)
        grid = None
        if check.startswith('grid='):
            line = open(check.split('=', 1)[1]).read().split('grid16:', 1)[1]
            grid = [int(v, 16) for v in line.split()]
            if len(grid) != 256:
                raise SystemExit('%s: grid reference needs 256 words, has %d' % (spec, len(grid)))
            check = 'grid'
        r = build(path, check, grid, inject)
        r['geometry'] = geometry
        page_rows = []
        for va in sorted(r['pages']):
            flat = [x for pair in r['pages'][va] for x in pair]
            sym = 'fp6_replay_%s_p%x' % (name, va)
            block = emit(sym, flat)
            if block:
                out.append(block)
            page_rows.append('\t{ 0x%xull, %s, %d },' % (va, sym if flat else 'NULL', len(flat) // 2))
        out.append('static const struct fp6_replay_page fp6_replay_%s_pages[] = {' % name)
        out.extend(page_rows)
        out.append('};')
        init = emit('fp6_replay_%s_init' % name, r['init'])
        if init:
            out.append(init)
        out.append(emit('fp6_replay_%s_steps' % name, r['steps'], 'uint16_t'))
        cbd = emit('fp6_replay_%s_cbd' % name, r['cbd'], 'uint64_t')
        if cbd:
            out.append(cbd)
        rows.append('\t{ "%s", fp6_replay_%s_pages, %d, 0x%xull, %d, FP6_REPLAY_CHECK_%s,\n'
                    '\t  0x%xull, %d, %s, fp6_replay_%s_steps, %d, %s, %d,' % (name, name, len(page_rows), r['ib_va'],
                                                r['ib_dwords'], check.upper(), r['check_va'],
                                                r['elements'],
                                                'fp6_replay_%s_init' % name if r['init'] else 'NULL',
                                                name, len(r['steps']),
                                                'fp6_replay_%s_cbd' % name if r['cbd'] else 'NULL',
                                                len(r['cbd'])) +
                    '\n\t  0x%xull, %d, 0x%xull, %d, %d, %d, %d, %d, %d },' % (
                        r['ib2_va'], r['ib2_dwords'], r['scanout_va'], r['scanout_bytes'], *r['geometry']))
        summary.append('%s: %d pages (%d with data) ib=0x%x/%d dwords check=%s'
                       % (name, len(page_rows), sum(1 for v in r['pages'].values() if v),
                          r['ib_va'], r['ib_dwords'], check))
    out.append('static const struct fp6_replay fp6_replays[] = {')
    out.extend(rows)
    out.append('};')
    out.append('#define FP6_REPLAY_COUNT (sizeof(fp6_replays) / sizeof(fp6_replays[0]))')
    out.append('#endif')
    open(out_path, 'w').write('\n'.join(out) + '\n')
    print('\n'.join(summary))


if __name__ == '__main__':
    main()
