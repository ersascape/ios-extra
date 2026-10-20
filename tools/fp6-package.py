#!/usr/bin/env python3
"""Package a CI FP6 kernel and matching ADT as a temporary Android v4 boot image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import mkpayload

ROOT = Path(__file__).resolve().parents[1]

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kernel', required=True, type=Path)
    ap.add_argument('--adt', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--dtb', type=Path, default=None)
    ap.add_argument('--header-version', default=None)
    ap.add_argument('--cmdline', default='debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress')
    ap.add_argument('--image-name', default='fp6-shim-boot.img')
    ap.add_argument('--commit', default='local')
    ap.add_argument('--ci-run', default='local')
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cmdline = args.cmdline
    payload, info = mkpayload.build(str(args.kernel), str(args.adt), cmdline)
    payload_path = out / 'fp6-payload.bin'
    payload_path.write_bytes(payload)
    hdr_ver = args.header_version or ('2' if args.dtb else '4')
    env = dict(os.environ, SHIM_BOOT_HEADER_VERSION=hdr_ver, SHIM_CPPFLAGS='-DSHIM_FP6=1')
    if args.dtb:
        env['SHIM_DTB'] = str(args.dtb.resolve())
    subprocess.run(['bash', str(ROOT / 'shim/build.sh'), str(payload_path)], env=env, check=True)
    image = out / args.image_name
    shutil.copyfile(ROOT / 'shim/out/shim-boot.img', image)
    if hdr_ver == '2':
        subprocess.run([sys.executable, str(ROOT / 'tools/unpack_bootv2.py'), str(image), str(out / 'check')], check=True)
        if (out / 'check/ramdisk').read_bytes() != payload:
            raise RuntimeError('packaged payload mismatch')
        if (out / 'check/kernel').read_bytes() != (ROOT / 'shim/out/Image').read_bytes():
            raise RuntimeError('packaged shim mismatch')
    sha = hashlib.sha256(image.read_bytes()).hexdigest()
    (out / 'SHA256SUMS').write_text(f'{sha}  {image.name}\n')
    manifest = dict(source_commit=args.commit, ci_run=args.ci_run, image=image.name,
                    sha256=sha, cmdline=cmdline, payload=info,
                    kernel_sha256=hashlib.sha256(args.kernel.read_bytes()).hexdigest(),
                    adt_sha256=hashlib.sha256(args.adt.read_bytes()).hexdigest(),
                    hardware_tested=False)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(image, sha)

if __name__ == '__main__':
    main()
