#!/usr/bin/env python3
"""One temporary-boot test cycle on the phone (Linux host, phone in fastboot).

  gpu-phone-test.py --image shim/out/shim-boot-0092-rpmhinit.img \\
      --sha256 HEX --name phone-0092-rpmhinit [--settle 40] [--logs DIR]

Steps: require exactly one fastboot device, verify the image hash, start our own
`tcpdump` of the phone's UDP log and tools/phone-ecm-host.py, `fastboot boot` the
image (serial never printed or stored), wait for the phone to answer ping, let the
cached GPU reports replay, stop only our own tcpdump, decode the log and print the
`SWEET GPU:` lines. Never runs `fastboot getvar`, never flashes, never reboots a
phone that is not already in fastboot. Uses `pkexec` for privileged host setup.
"""
import argparse
import hashlib
from pathlib import Path
import select
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOGS = Path('/run/media/dipa/android/ios-extra-work/logs')


def fastboot_devices():
    result = subprocess.run(['fastboot', 'devices'], capture_output=True, text=True)
    return [line.split()[0] for line in result.stdout.splitlines() if line.strip()]


def ping(host='192.168.7.2'):
    return subprocess.run(['ping', '-c1', '-W1', host], capture_output=True).returncode == 0


def boot_checked(devices, image, logs, name):
    # Recheck after capture setup and directly before the only boot command.
    current = fastboot_devices()
    if len(current) != 1 or current != devices:
        raise SystemExit('fastboot target changed before boot; refusing to boot')
    boot = subprocess.run(['fastboot', '-s', current[0], 'boot', str(image)],
                          capture_output=True, text=True)
    output = (boot.stdout + boot.stderr).replace(current[0], '<serial>')
    (logs / (name + '-fastboot.txt')).write_text(output)
    print(output.strip())
    if boot.returncode:
        raise SystemExit('fastboot boot failed')
    print('boot issued', time.strftime('%H:%M:%S UTC', time.gmtime()))


def run_user_capture(args, devices):
    raw = args.logs / (args.name + '.udp')
    log = args.logs / (args.name + '.txt')
    host = subprocess.Popen(
        [sys.executable, str(ROOT / 'tools/phone-ecm-user.py'), '--capture', str(raw),
         '--timeout', '90', '--capture-seconds', '65', '--max-packets', '5000'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    try:
        ready_deadline = time.monotonic() + 120
        while time.monotonic() < ready_deadline:
            if select.select([host.stdout], [], [], 0.25)[0]:
                line = host.stdout.readline()
                if line:
                    print(line.strip())
                    if line.strip() == 'USER HELPER READY':
                        break
            if host.poll() is not None:
                stdout, stderr = host.communicate()
                raise SystemExit('user capture helper failed before boot: ' +
                                 (stderr.strip() or stdout.strip()))
        else:
            raise SystemExit('user capture helper did not become ready; refusing to boot')

        boot_checked(devices, args.image, args.logs, args.name)
        deadline = time.monotonic() + 90
        next_ping = 0.0
        ping_seen = False
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_ping:
                ping_seen = ping()
                if ping_seen:
                    break
                next_ping = now + 2
            time.sleep(0.1)
        print('phone answers ping:', ping_seen)
        if ping_seen:
            time.sleep(args.settle)
    finally:
        try:
            host.wait(timeout=160)
        except subprocess.TimeoutExpired:
            host.terminate()
            try:
                host.wait(timeout=5)
            except subprocess.TimeoutExpired:
                host.kill()
                host.wait()
            print('user capture helper exceeded its bound and was stopped')
    if host.poll() is not None:
        stdout, stderr = host.communicate()
        if stdout.strip():
            print(stdout.strip())
        if stderr.strip():
            print(stderr.strip(), file=sys.stderr)
    if raw.exists():
        subprocess.run([sys.executable, str(ROOT / 'tools/gpu-decode-pcap.py'), str(raw),
                        '--raw-udp', '--out', str(log)])
    else:
        print('no USB UDP capture file was produced', file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--name', required=True, help='log base name, e.g. phone-0092-rpmhinit')
    parser.add_argument('--settle', type=float, default=40, help='seconds to wait after ping')
    parser.add_argument('--logs', type=Path, default=DEFAULT_LOGS)
    parser.add_argument('--capture-mode', choices=('pkexec', 'user'), default='pkexec',
                        help='host USB capture setup; user mode uses the existing '
                             'fp6-usb-log NetworkManager profile')
    parser.add_argument('--stop-pcap', type=Path,
                        help='stop a stale tcpdump only if its command names this pcap')
    args = parser.parse_args()

    if hashlib.sha256(args.image.read_bytes()).hexdigest() != args.sha256:
        raise SystemExit('image hash mismatch; refusing to boot')
    devices = fastboot_devices()
    if len(devices) != 1:
        raise SystemExit('need exactly one fastboot device, found %d (put the phone in fastboot)'
                         % len(devices))
    args.logs.mkdir(parents=True, exist_ok=True)
    if args.capture_mode == 'user':
        if args.stop_pcap:
            parser.error('--stop-pcap is only supported with pkexec capture mode')
        run_user_capture(args, devices)
        return
    pcap = args.logs / (args.name + '.pcap')
    host = subprocess.Popen(
        ['pkexec', sys.executable, str(ROOT / 'tools/phone-ecm-host.py'),
         '--timeout', '90', '--capture', str(pcap), '--capture-seconds', '65',
         '--max-packets', '5000',
         *(('--stop-pcap', str(args.stop_pcap)) if args.stop_pcap else ())],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    try:
        # Wait for the single pkexec authorization before touching the phone.
        # If it is denied or times out, do not issue fastboot boot.
        auth_deadline = time.monotonic() + 120
        while time.monotonic() < auth_deadline:
            if select.select([host.stdout], [], [], 0.25)[0]:
                line = host.stdout.readline()
                if line:
                    print(line.strip())
                    if line.strip() == 'ROOT HELPER READY':
                        break
            if host.poll() is not None:
                stdout, stderr = host.communicate()
                raise SystemExit('root capture helper failed before boot: ' +
                                 (stderr.strip() or stdout.strip()))
        else:
            raise SystemExit('root capture authorization did not complete; refusing to boot')
        boot_checked(devices, args.image, args.logs, args.name)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and not ping():
            time.sleep(2)
        print('phone answers ping:', ping())
        time.sleep(args.settle)
    finally:
        try:
            host.wait(timeout=100)
        except subprocess.TimeoutExpired:
            # The root helper has a fixed interface and capture bound and will
            # stop tcpdump itself without another authorization request.
            print('capture helper is still inside its bounded timeout')
    if host.poll() is not None:
        stdout, stderr = host.communicate()
        if stdout.strip():
            print(stdout.strip())
        if stderr.strip():
            print(stderr.strip(), file=sys.stderr)
    subprocess.run([sys.executable, str(ROOT / 'tools/gpu-decode-pcap.py'), str(pcap)])


if __name__ == '__main__':
    main()
