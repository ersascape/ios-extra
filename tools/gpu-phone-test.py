#!/usr/bin/env python3
"""One temporary-boot test cycle on the phone (Linux host, phone in fastboot).

  gpu-phone-test.py --image shim/out/shim-boot-0092-rpmhinit.img \\
      --sha256 HEX --name phone-0092-rpmhinit [--settle 40] [--logs DIR]

Steps: require exactly one fastboot device, verify the image hash, start our own
`tcpdump` of the phone's UDP log and tools/phone-ecm-host.py, `fastboot boot` the
image (serial never printed or stored), wait for the phone to answer ping, let the
cached GPU reports replay, stop only our own tcpdump, decode the log and print the
`SWEET GPU:` lines. Never runs `fastboot getvar`, never flashes, never reboots a
phone that is not already in fastboot. Needs `sudo -n tcpdump`.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOGS = Path('/run/media/dipa/android/ios-extra-work/logs')


def fastboot_devices():
    result = subprocess.run(['fastboot', 'devices'], capture_output=True, text=True)
    return [line.split()[0] for line in result.stdout.splitlines() if line.strip()]


def our_tcpdump_pids(marker):
    pids = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if (proc / 'comm').read_text().strip() != 'tcpdump':
                continue
            if marker in (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode():
                pids.append(proc.name)
        except OSError:
            continue
    return pids


def ping(host='192.168.7.2'):
    return subprocess.run(['ping', '-c1', '-W1', host], capture_output=True).returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--name', required=True, help='log base name, e.g. phone-0092-rpmhinit')
    parser.add_argument('--settle', type=float, default=40, help='seconds to wait after ping')
    parser.add_argument('--logs', type=Path, default=DEFAULT_LOGS)
    args = parser.parse_args()

    if hashlib.sha256(args.image.read_bytes()).hexdigest() != args.sha256:
        raise SystemExit('image hash mismatch; refusing to boot')
    devices = fastboot_devices()
    if len(devices) != 1:
        raise SystemExit('need exactly one fastboot device, found %d (put the phone in fastboot)'
                         % len(devices))
    args.logs.mkdir(parents=True, exist_ok=True)
    pcap = args.logs / (args.name + '.pcap')
    tcpdump = subprocess.Popen(
        ['sudo', '-n', 'tcpdump', '-U', '-n', '-i', 'any', '-s0', '-w', str(pcap),
         'udp and src host 192.168.7.2 and dst port 5140'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ecm = None
    try:
        time.sleep(2)
        ecm = subprocess.Popen([sys.executable, str(ROOT / 'tools/phone-ecm-host.py'),
                                '--timeout', '120'], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        boot = subprocess.run(['fastboot', '-s', devices[0], 'boot', str(args.image)],
                              capture_output=True, text=True)
        text = (boot.stdout + boot.stderr).replace(devices[0], '<serial>')
        (args.logs / (args.name + '-fastboot.txt')).write_text(text)
        print(text.strip())
        if boot.returncode:
            raise SystemExit('fastboot boot failed')
        print('boot issued', time.strftime('%H:%M:%S UTC', time.gmtime()))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and not ping():
            time.sleep(2)
        print('phone answers ping:', ping())
        time.sleep(args.settle)
    finally:
        if ecm:
            ecm.terminate()
        for pid in our_tcpdump_pids(str(pcap)):
            subprocess.run(['sudo', '-n', 'kill', pid])
        tcpdump.wait(timeout=10)
    subprocess.run([sys.executable, str(ROOT / 'tools/gpu-decode-pcap.py'), str(pcap)])


if __name__ == '__main__':
    main()
