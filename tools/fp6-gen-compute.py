#!/usr/bin/env python3
"""Turn Mesa freedreno `.rd` captures of computerator dispatches into the C data
header used by the FP6 compute probe.

Capture each kernel on a host with the pinned Mesa build (see
docs/FP6_METAL_PORT_MAP.md):

  LD_PRELOAD=libfreedreno_noop_drm_shim.so FD_GPU_ID=810 \\
  FD_RD_DUMP=enable,full FD_RD_DUMP_PATH=DIR \\
  computerator -f examples/KERNEL.asm -g X,Y,Z

then run:

  fp6-gen-compute.py OUT.h NAME:CAPTURE.rd:EXPECT [NAME:CAPTURE.rd:EXPECT ...]

EXPECT names how the probe checks the result buffer: add5 (initial + 5 per run),
iota (buf[i] == i), branch (buf[0] == 0x87654321, the rest 0x12345678), const5
(every element == 5).

The streams hold Mesa's fake IOVAs. This tool records where the shader, the UAV
descriptor and the two event addresses sit so the kernel can patch real GPU
addresses in, and keeps the shader words, the 16-dword buffer descriptor and the
initial data of each kernel.
"""
import gzip
import re
import struct
import sys

RD_GPUADDR, RD_BUFFER_CONTENTS, RD_CMDSTREAM_ADDR, RD_CHIP_ID = 3, 12, 6, 14
EXPECT = {'add5': 0, 'iota': 1, 'branch': 2, 'const5': 3}
GROUPS = ('shader', 'uav', 'scratch', 'control')


def parse(path):
    data = gzip.open(path).read()
    off, bos, cur, cmd, chip = 0, [], None, None, None
    while off < len(data):
        kind, size = struct.unpack_from('<II', data, off)
        off += 8
        payload = data[off:off + size]
        off += size
        if kind == RD_GPUADDR:
            cur = struct.unpack_from('<II', payload)
        elif kind == RD_BUFFER_CONTENTS:
            bos.append((cur[0], cur[1], payload))
        elif kind == RD_CMDSTREAM_ADDR:
            cmd = struct.unpack_from('<II', payload)
        elif kind == RD_CHIP_ID:
            chip = struct.unpack_from('<I', payload)[0]
    return bos, cmd, chip


def words(blob):
    return list(struct.unpack('<%dI' % (len(blob) // 4), blob))


def find_bo(bos, addr):
    for base, size, blob in bos:
        if base <= addr < base + size:
            return base, blob
    raise SystemExit('no BO holds 0x%x' % addr)


def pointer_slots(stream, bos):
    """{address: [(lo_index, hi_index), ...]} for every pointer operand into a BO.

    CP_LOAD_STATE6, CP_EVENT_WRITE7 and CP_WAIT_REG_MEM store lo, hi back to
    back; CP_CONTEXT_REG_BUNCH stores reg, lo, reg+1, hi. Anything else that
    merely looks like an address (masks, values) is not a pointer slot.
    """
    def inside(v):
        return any(b <= v < b + sz for b, sz, _ in bos)

    out = {}
    for i, w in enumerate(stream[:-2]):
        if not inside(w):
            continue
        if stream[i + 1] == 0:
            out.setdefault(w, []).append((i, i + 1))
        elif i and stream[i - 1] < 0x10000 and stream[i + 1] < 0x10000 and stream[i + 2] == 0:
            out.setdefault(w, []).append((i, i + 2))
    return out


def build_test(path):
    bos, cmd, chip = parse(path)
    if chip != 0x44010000:
        raise SystemExit('%s is not an A810 capture: chip 0x%x' % (path, chip or 0))
    cmd_addr, cmd_dwords = cmd
    base, blob = find_bo(bos, cmd_addr)
    start = cmd_addr - base
    stream = words(blob[start:start + cmd_dwords * 4])
    named = pointer_slots(stream, bos)
    contents = {a: p for a, _, p in bos}
    if len(named) != 4:
        raise SystemExit('%s: expected shader, UAV, scratch and control pointers, found %s'
                         % (path, sorted(hex(v) for v in named)))
    # The UAV descriptor has TYPE=TEX_BUFFER (bits 17..19 == 4) and a nonzero count.
    uav = next(a for a in named if a in contents
               and (words(contents[a])[1] >> 17) & 7 == 4 and words(contents[a])[2])
    shader = next(a for a in named if a in contents and a != uav and any(contents[a]))
    scratch, control = sorted(a for a in named if a not in (uav, shader))
    sw = words(contents[shader])
    last = max(i for i, w in enumerate(sw) if w)
    shader_words = sw[:((last // 16) + 1) * 16]
    desc = words(contents[uav])[:16]
    buf_iova = desc[0] | ((desc[1] & 0x1ffff) << 32)
    buf_base, buf_blob = find_bo(bos, buf_iova)
    elements = desc[2] & 0x7fff
    data = words(buf_blob[buf_iova - buf_base:buf_iova - buf_base + elements * 4])
    addr_of = {'shader': shader, 'uav': uav, 'scratch': scratch, 'control': control}
    return {'stream': stream, 'shader': shader_words, 'uav': desc, 'data': data,
            'relocs': {g: named[addr_of[g]] for g in GROUPS}, 'elements': elements}


def emit_array(name, values, per_line=8, kind='uint32_t', width=8):
    suffix = 'u' if kind == 'uint32_t' else ''
    lines = ['static const %s %s[%d] = {' % (kind, name, len(values))]
    for i in range(0, len(values), per_line):
        chunk = ', '.join('0x%0*x%s' % (width, v, suffix) for v in values[i:i + per_line])
        lines.append('\t' + chunk + ',')
    lines.append('};')
    return '\n'.join(lines)


def main():
    if len(sys.argv) < 3:
        raise SystemExit('usage: fp6-gen-compute.py OUT.h NAME:CAPTURE.rd:EXPECT ...')
    out_path, specs = sys.argv[1], sys.argv[2:]
    out = ['/* Generated by tools/fp6-gen-compute.py from Mesa freedreno A810 captures of',
           ' * computerator kernels. Do not edit; regenerate. Addresses in each stream are',
           ' * Mesa shim IOVAs that the probe replaces through the relocation tables. */',
           '#ifndef FP6_GPU_COMPUTE_TESTS_H',
           '#define FP6_GPU_COMPUTE_TESTS_H',
           '#define FP6_CS_EXPECT_ADD5   %du' % EXPECT['add5'],
           '#define FP6_CS_EXPECT_IOTA   %du' % EXPECT['iota'],
           '#define FP6_CS_EXPECT_BRANCH %du' % EXPECT['branch'],
           '#define FP6_CS_EXPECT_CONST5 %du' % EXPECT['const5'],
           'struct fp6_cs_test {',
           '\tconst char *name;',
           '\tconst uint32_t *stream;',
           '\tunsigned stream_dwords;',
           '\tconst uint32_t *shader;',
           '\tunsigned shader_dwords;',
           '\tconst uint32_t *uav;',
           '\tconst uint32_t *data;',
           '\tunsigned elements;',
           '\tunsigned expect;',
           '\tconst uint16_t *reloc[4]; /* shader, uav, scratch, control: lo/hi index pairs */',
           '\tunsigned reloc_pairs[4];',
           '};']
    rows, summary, longest = [], [], 0
    for spec in specs:
        name, path, expect = spec.split(':')
        if expect not in EXPECT or not re.fullmatch(r'[a-z0-9_]+', name):
            raise SystemExit('bad spec %r' % spec)
        t = build_test(path)
        longest = max(longest, len(t['stream']))
        out.append(emit_array('fp6_cs_%s_stream' % name, t['stream']))
        out.append(emit_array('fp6_cs_%s_shader' % name, t['shader']))
        out.append(emit_array('fp6_cs_%s_uav' % name, t['uav']))
        out.append(emit_array('fp6_cs_%s_data' % name, t['data']))
        for g in GROUPS:
            flat = [v for pair in t['relocs'][g] for v in pair]
            out.append(emit_array('fp6_cs_%s_%s_reloc' % (name, g), flat, 8, 'uint16_t', 4))
        rows.append('\t{ "%s", fp6_cs_%s_stream, %d, fp6_cs_%s_shader, %d, fp6_cs_%s_uav,\n'
                    '\t  fp6_cs_%s_data, %d, FP6_CS_EXPECT_%s,\n'
                    '\t  { %s },\n\t  { %s } },'
                    % (name, name, len(t['stream']), name, len(t['shader']), name, name,
                       t['elements'], expect.upper(),
                       ', '.join('fp6_cs_%s_%s_reloc' % (name, g) for g in GROUPS),
                       ', '.join(str(len(t['relocs'][g])) for g in GROUPS)))
        summary.append('%s: stream=%d shader=%d elements=%d' %
                       (name, len(t['stream']), len(t['shader']), t['elements']))
    out.append('static const struct fp6_cs_test fp6_cs_tests[] = {')
    out.extend(rows)
    out.append('};')
    out.append('#define FP6_CS_TEST_COUNT (sizeof(fp6_cs_tests) / sizeof(fp6_cs_tests[0]))')
    out.append('#define FP6_CS_MAX_STREAM %uu' % longest)
    out.append('#endif')
    open(out_path, 'w').write('\n'.join(out) + '\n')
    print('\n'.join(summary))


if __name__ == '__main__':
    main()
