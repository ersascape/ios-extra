#!/usr/bin/env python3
"""Extract the phone's UDP kernel log (192.168.7.2 -> port 5140) from a pcap,
or from a user-mode capture's concatenated UDP payload file.

  gpu-decode-pcap.py CAPTURE [--raw-udp] [--out LOG.txt] [--show REGEX] [--all]

Writes the reassembled text log next to the capture (or --out) and prints the
interesting lines: `SWEET GPU:` lines (deduplicated unless --all; the USB logger
replays the cached report several times), panics and anything matching --show.
Handles Linux cooked (113/276) and Ethernet (1) captures.
"""
import argparse
from pathlib import Path
import re
import struct
import sys

PHONE = bytes([192, 168, 7, 2])
ENDIAN = {b'\xd4\xc3\xb2\xa1': '<', b'\xa1\xb2\xc3\xd4': '>',
          b'\x4d\x3c\xb2\xa1': '<', b'\xa1\xb2\x3c\x4d': '>'}


def udp_payloads(buf):
    end = ENDIAN.get(bytes(buf[:4]))
    if end is None or len(buf) < 24:
        raise SystemExit('not a pcap (or empty capture)')
    link = struct.unpack_from(end + 'I', buf, 20)[0]
    pos = 24
    while pos + 16 <= len(buf):
        length = struct.unpack_from(end + '4I', buf, pos)[2]
        if pos + 16 + length > len(buf):
            break
        packet = buf[pos + 16:pos + 16 + length]
        pos += 16 + length
        if link == 276:
            offset, proto = 20, int.from_bytes(packet[:2], 'big')
        elif link == 113:
            offset, proto = 16, int.from_bytes(packet[14:16], 'big')
        elif link == 1:
            offset, proto = 14, int.from_bytes(packet[12:14], 'big')
        else:
            raise SystemExit('unsupported pcap link type %d' % link)
        if proto != 0x800:
            continue
        ip = packet[offset:]
        if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 17 or ip[12:16] != PHONE:
            continue
        hlen = (ip[0] & 15) * 4
        if hlen < 20 or len(ip) < hlen + 8:
            continue
        udp = ip[hlen:]
        if int.from_bytes(udp[2:4], 'big') != 5140:
            continue
        length = int.from_bytes(udp[4:6], 'big')
        if length >= 8:
            yield udp[8:length]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('pcap', type=Path)
    parser.add_argument('--raw-udp', action='store_true',
                        help='input is concatenated UDP payloads, not a pcap')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--show', help='extra regex of lines to print')
    parser.add_argument('--all', action='store_true', help='do not deduplicate printed lines')
    args = parser.parse_args()
    data = args.pcap.read_bytes()
    parts = [data] if args.raw_udp else list(udp_payloads(data))
    out = args.out or args.pcap.with_suffix('.txt')
    out.write_bytes(b''.join(parts))
    print('captured UDP packets:', len(parts), 'log bytes:', out.stat().st_size, file=sys.stderr)
    want = re.compile(r'SWEET GPU:|panic\(cpu|SWEET EARLY PANIC' +
                      ('|' + args.show if args.show else ''))
    seen = set()
    for line in out.read_text(errors='replace').splitlines():
        if want.search(line) and (args.all or line not in seen):
            seen.add(line)
            print(line)


if __name__ == '__main__':
    main()
