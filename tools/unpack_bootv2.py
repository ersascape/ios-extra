#!/usr/bin/env python3
"""Unpack Android boot image headers v0-v2 and v4 into components + header.txt."""
import struct, sys, os
src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
b = open(src, 'rb').read()
assert b[:8] == b'ANDROID!'
if len(b) >= 4096 and struct.unpack_from('<I', b, 40)[0] == 4:
    ks, rs, osv, hs = struct.unpack_from('<4I', b, 8)
    ver, = struct.unpack_from('<I', b, 40)
    cmd = b[44:44+1536].split(b'\0')[0].decode()
    sig, = struct.unpack_from('<I', b, 1580)
    assert hs == 1584 and sig == 0, 'unsupported v4 header size or boot signature'
    ko = 4096
    ro = ko + ((ks + 4095) // 4096) * 4096
    assert ro + rs <= len(b), 'truncated v4 image'
    open(f'{out}/kernel', 'wb').write(b[ko:ko+ks])
    open(f'{out}/ramdisk', 'wb').write(b[ro:ro+rs])
    info = dict(kernel_size=ks, ramdisk_size=rs, os_version=hex(osv), header_version=ver,
                header_size=hs, signature_size=sig, page_size=4096, cmdline=cmd,
                kernel_offset=ko, ramdisk_offset=ro, dtb='provided by device vendor_boot')
    with open(f'{out}/header.txt', 'w') as f:
        for k, v in info.items(): f.write(f'{k}: {v}\n')
    print(open(f'{out}/header.txt').read())
    raise SystemExit(0)
(ks, ka, rs, ra, ss, sa, ta, ps, ver, osv) = struct.unpack_from('<10I', b, 8)
cmd = b[64:64+512].split(b'\0')[0] + b[608:608+1024].split(b'\0')[0]
info = dict(kernel_size=ks, kernel_addr=hex(ka), ramdisk_size=rs, ramdisk_addr=hex(ra),
            second_size=ss, tags_addr=hex(ta), page_size=ps, header_version=ver,
            os_version=hex(osv), name=b[48:64].split(b'\0')[0].decode(), cmdline=cmd.decode())
rnd = lambda n: (n + ps - 1) // ps * ps
off = ps
parts = [('kernel', ks), ('ramdisk', rs), ('second', ss)]
if ver >= 1:
    rds, rdo, hs = struct.unpack_from('<IQI', b, 1632)
    parts.append(('recovery_dtbo', rds)); info['header_size'] = hs
if ver >= 2:
    ds, da = struct.unpack_from('<IQ', b, 1648)
    parts.append(('dtb', ds)); info['dtb_addr'] = hex(da)
for name, sz in parts:
    if sz:
        open(f'{out}/{name}', 'wb').write(b[off:off+sz])
    info[name + '_offset'] = off
    off += rnd(sz)
with open(f'{out}/header.txt', 'w') as f:
    for k, v in info.items():
        f.write(f'{k}: {v}\n')
print(open(f'{out}/header.txt').read())
