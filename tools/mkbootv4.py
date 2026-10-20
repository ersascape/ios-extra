#!/usr/bin/env python3
"""Create an unsigned Android boot header v4 image for temporary fastboot boot.

The device's existing vendor_boot supplies the FP6 DTB and vendor ramdisk.
This image carries only the shim kernel and its XNU payload ramdisk.
"""
import argparse
from pathlib import Path
import struct

PAGE = 4096
HEADER_SIZE = 1584


def pad(data):
    return data + b'\0' * (-len(data) % PAGE)


def build(kernel, ramdisk, cmdline):
    kernel = Path(kernel).read_bytes()
    ramdisk = Path(ramdisk).read_bytes()
    command = cmdline.encode('ascii')
    if len(command) >= 1536:
        raise ValueError('boot command line must fit in 1535 bytes')
    if not kernel or not ramdisk:
        raise ValueError('boot v4 requires a non-empty kernel and ramdisk')
    header = struct.pack('<8s9I1536sI', b'ANDROID!', len(kernel), len(ramdisk),
                         0, HEADER_SIZE, 0, 0, 0, 0, 4,
                         command + b'\0' * (1536 - len(command)), 0)
    assert len(header) == HEADER_SIZE
    return pad(header) + pad(kernel) + pad(ramdisk)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kernel', required=True, type=Path)
    ap.add_argument('--ramdisk', required=True, type=Path)
    ap.add_argument('--cmdline', default='console=null')
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    args.output.write_bytes(build(args.kernel, args.ramdisk, args.cmdline))
    print(f'{args.output}: {args.output.stat().st_size} bytes (Android boot v4, no embedded DTB)')


if __name__ == '__main__':
    main()
