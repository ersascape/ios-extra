#!/usr/bin/env python3
"""Package a CI-built kernel into a temporary `fastboot boot` image.

  gpu-package.py --kernel out-0092/kernel.development.sweet --patch 0092 \\
      --mode 10 --name rpmhinit --ci-run 39171199100 --commit SHA

Writes shim/out/shim-boot-<patch>-<name>.img (+ payload, unpack check, manifest),
verifies the unpacked ramdisk equals the payload and the command line round-trips,
and prints the SHA256. Boot arguments are the established UFS-root set plus
`sweetgpu=<mode>`. Uses the stock-derived high-RAM ADT (default
shim/out/sweet-0082hi.adt, identical for 0081 onward). Nothing is flashed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import mkpayload  # noqa: E402

BOOT_ARGS = ('debug=0xc serial=3 cpus=6 keepsyms=1 -enable_kprintf_spam -noprogress '
             'rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 '
             'wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 '
             'wdt=-1 sweetfb_noconsole=1 sweetfb_hz=30 sweetusb=2')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--patch', required=True, help='patch number, e.g. 0092')
    parser.add_argument('--mode', type=int, required=True, help='sweetgpu= value')
    parser.add_argument('--name', required=True, help='short image label')
    parser.add_argument('--ci-run', type=int, required=True)
    parser.add_argument('--commit', required=True, help='source commit the CI run built')
    parser.add_argument('--adt', type=Path, default=ROOT / 'shim/out/sweet-0082hi.adt')
    args = parser.parse_args()

    out = ROOT / 'shim/out'
    cmdline = BOOT_ARGS + f' sweetgpu={args.mode}'
    assert len(cmdline.encode()) < mkpayload.BOOT_LINE_LENGTH, 'boot line too long'
    payload = out / f'payload-{args.patch}-{args.name}.bin'
    blob, info = mkpayload.build(str(args.kernel), str(args.adt), cmdline)
    payload.write_bytes(blob)
    subprocess.run(['bash', str(ROOT / 'shim/build.sh'), str(payload)], cwd=ROOT, check=True)
    image = out / f'shim-boot-{args.patch}-{args.name}.img'
    shutil.copyfile(out / 'shim-boot.img', image)
    unpack = out / f'check-{args.patch}-{args.name}'
    subprocess.run([sys.executable, str(ROOT / 'tools/unpack_bootv2.py'), str(image), str(unpack)],
                   check=True)
    assert (unpack / 'ramdisk').read_bytes() == blob, 'ramdisk differs from payload'
    assert blob[0x48:0x48 + 608].split(b'\0')[0].decode() == cmdline, 'cmdline mismatch'
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    manifest = {'ci_run': args.ci_run, 'source_commit': args.commit, 'images': [{
        'path': str(image), 'sha256': digest, 'bytes': image.stat().st_size,
        'cmdline': cmdline, 'payload': info}]}
    manifest_path = out / f'manifest-{args.patch}.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(args.name, digest, image.stat().st_size)
    print(manifest_path)


if __name__ == '__main__':
    main()
