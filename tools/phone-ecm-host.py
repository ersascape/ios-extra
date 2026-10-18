#!/usr/bin/env python3
"""Wait for sweet's USB ECM interface and configure the host logging address.

Linux only. Match the phone's fixed ECM MAC, retrying when udev renames usb0.
Requires nmcli and passwordless sudo for the existing ip commands.
"""
import argparse
from pathlib import Path
import subprocess
import time


def interfaces(mac):
    for path in Path('/sys/class/net').iterdir():
        try:
            if (path / 'address').read_text().strip().lower() == mac:
                yield path.name
        except OSError:
            continue  # Interface disappeared or was renamed during discovery.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    mac = '02:00:5e:77:ee:01'
    deadline = time.monotonic() + args.timeout
    last_error = 'phone interface has not appeared'
    while time.monotonic() < deadline:
        names = list(interfaces(mac))
        if len(names) == 1:
            name = names[0]
            commands = [
                ['nmcli', 'dev', 'set', name, 'managed', 'no'],
                ['sudo', '-n', 'ip', 'addr', 'replace', '192.168.7.1/24', 'dev', name],
                ['sudo', '-n', 'ip', 'link', 'set', name, 'up'],
            ]
            try:
                for command in commands:
                    subprocess.run(command, check=True, capture_output=True,
                                   text=True, timeout=5)
                if name in interfaces(mac):
                    print(f'USB ECM host ready: {name}, 192.168.7.1/24', flush=True)
                    return 0
            except (OSError, subprocess.SubprocessError) as error:
                last_error = str(error)
                # A usb0 -> enp... rename can invalidate any command above.
        elif len(names) > 1:
            last_error = 'multiple interfaces match the phone ECM MAC'
        time.sleep(0.1)
    parser.exit(1, f'USB ECM host setup timed out: {last_error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
