#!/usr/bin/env python3
"""Root helper for one bounded USB ECM setup and kernel-log capture.

Called once through pkexec by gpu-phone-test.py. It removes a specifically
identified stale capture if requested, waits for the phone's fixed ECM MAC,
configures the host address once, captures UDP logs, then exits on a time or
packet bound. Setup failure is reported immediately; authorization is never
retried in a loop.
"""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import time


def interfaces(mac):
    for path in Path('/sys/class/net').iterdir():
        try:
            if (path / 'address').read_text().strip().lower() == mac:
                yield path.name
        except OSError:
            continue  # Interface disappeared or was renamed during discovery.


def stop_capture(marker):
    """Stop only a tcpdump whose command line names the requested pcap."""
    matches = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if (proc / 'comm').read_text().strip() != 'tcpdump':
                continue
            command = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode()
            if marker in command:
                matches.append(int(proc.name))
        except OSError:
            continue
    for pid in matches:
        try:
            os.kill(pid, signal.SIGINT)
        except ProcessLookupError:
            continue
    deadline = time.monotonic() + 5
    while matches and time.monotonic() < deadline:
        matches = [pid for pid in matches if Path(f'/proc/{pid}').exists()]
        if matches:
            time.sleep(0.05)
    if matches:
        raise RuntimeError('stale tcpdump did not stop within five seconds')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--capture-seconds', type=float, default=65)
    parser.add_argument('--max-packets', type=int, default=5000)
    parser.add_argument('--stop-pcap', type=Path)
    args = parser.parse_args()
    if args.timeout <= 0 or args.capture_seconds <= 0 or args.max_packets <= 0:
        parser.error('timeouts and max-packets must be positive')
    if os.geteuid() != 0:
        parser.error('this helper must be launched once through pkexec')
    if not args.capture.parent.is_dir():
        parser.error('capture directory must be created by the caller')
    if args.stop_pcap:
        stop_capture(str(args.stop_pcap))
        print('stopped stale capture', flush=True)
    print('ROOT HELPER READY', flush=True)
    mac = '02:00:5e:77:ee:01'
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        names = list(interfaces(mac))
        if len(names) == 1:
            name = names[0]
            try:
                subprocess.run(['nmcli', 'dev', 'set', name, 'managed', 'no'],
                               check=True, capture_output=True, text=True, timeout=5)
                subprocess.run(['ip', 'addr', 'replace', '192.168.7.1/24', 'dev', name],
                               check=True, capture_output=True, text=True, timeout=5)
                subprocess.run(['ip', 'link', 'set', name, 'up'],
                               check=True, capture_output=True, text=True, timeout=5)
            except (OSError, subprocess.SubprocessError) as error:
                parser.exit(1, f'USB ECM setup failed once on {name}: {error}\n')
            if name not in interfaces(mac):
                parser.exit(1, f'USB ECM interface changed during setup: {name}\n')
            print(f'USB ECM host ready: {name}, 192.168.7.1/24', flush=True)
            command = ['tcpdump', '-U', '-n', '-i', 'any', '-s0', '-c',
                       str(args.max_packets), '-w', str(args.capture),
                       'udp and src host 192.168.7.2 and dst port 5140']
            capture = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            capture_deadline = time.monotonic() + args.capture_seconds
            while capture.poll() is None and time.monotonic() < capture_deadline:
                time.sleep(0.1)
            if capture.poll() is None:
                capture.send_signal(signal.SIGINT)
            try:
                status = capture.wait(timeout=5)
            except subprocess.TimeoutExpired:
                capture.kill()
                capture.wait()
                parser.exit(1, 'tcpdump failed to stop cleanly\n')
            print(f'USB log capture complete packets_limit={args.max_packets} status={status}',
                  flush=True)
            return 0 if status == 0 else status
        elif len(names) > 1:
            parser.exit(1, 'multiple interfaces match the phone ECM MAC\n')
        time.sleep(0.1)
    parser.exit(1, 'USB ECM interface did not appear before timeout\n')


if __name__ == '__main__':
    raise SystemExit(main())
