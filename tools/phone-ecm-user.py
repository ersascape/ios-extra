#!/usr/bin/env python3
"""Bounded unprivileged USB-ECM UDP log capture using NetworkManager.

The phone's log protocol sends UDP payloads from 192.168.7.2 to host port 5140.
The existing fp6-usb-log NetworkManager profile supplies 192.168.7.1/24.
This helper never changes a profile or invokes an elevation tool.
"""
import argparse
import select
import socket
import subprocess
import time
from pathlib import Path

PHONE_MAC = '02:00:5e:77:ee:01'
PHONE_IP = '192.168.7.2'
HOST_IP = '192.168.7.1/24'
PROFILE = 'fp6-usb-log'


def interfaces(mac=PHONE_MAC):
    for path in Path('/sys/class/net').iterdir():
        try:
            if (path / 'address').read_text().strip().lower() == mac:
                yield path.name
        except OSError:
            continue


def validate_profile():
    fields = subprocess.run(
        ['nmcli', '-g',
         'connection.interface-name,connection.permissions,connection.autoconnect,'
         'ipv4.method,ipv4.addresses', 'connection', 'show', PROFILE],
        check=True, capture_output=True, text=True, timeout=5).stdout.splitlines()
    if len(fields) != 5:
        raise RuntimeError('fp6-usb-log profile returned an unexpected field list')
    iface, permissions, autoconnect, method, addresses = fields
    if not iface or (permissions and permissions != '--') or autoconnect != 'yes' or \
            method != 'manual' or HOST_IP not in addresses.split(','):
        raise RuntimeError('fp6-usb-log profile does not match the expected unprivileged setup')
    grants = subprocess.run(
        ['nmcli', '-t', '-g', 'PERMISSION,VALUE', 'general', 'permissions'],
        check=True, capture_output=True, text=True, timeout=5).stdout.splitlines()
    if 'org.freedesktop.NetworkManager.network-control:yes' not in grants:
        raise RuntimeError('NetworkManager network-control is not allowed for this account')
    return iface


def activate_profile(iface):
    def address_ready():
        active = subprocess.run(['nmcli', '-g', 'GENERAL.CONNECTION', 'device', 'show', iface],
                                check=True, capture_output=True, text=True,
                                timeout=5).stdout.strip()
        address = subprocess.run(['nmcli', '-g', 'IP4.ADDRESS', 'device', 'show', iface],
                                 check=True, capture_output=True, text=True,
                                 timeout=5).stdout.splitlines()
        return active == PROFILE and HOST_IP in address

    # Autoconnect may win the race against this helper. Avoid reactivation if
    # it has already installed the expected address.
    if address_ready():
        return
    result = subprocess.run(['nmcli', '--wait', '10', 'connection', 'up', 'id', PROFILE,
                             'ifname', iface], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError('NetworkManager could not activate fp6-usb-log: ' +
                           (result.stderr.strip() or result.stdout.strip()))
    if not address_ready():
        raise RuntimeError('fp6-usb-log is active but 192.168.7.1/24 is not configured')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True,
                        help='output concatenated UDP payload file')
    parser.add_argument('--timeout', type=float, default=90,
                        help='maximum wait for the phone ECM interface')
    parser.add_argument('--capture-seconds', type=float, default=65)
    parser.add_argument('--max-packets', type=int, default=5000)
    parser.add_argument('--check-only', action='store_true',
                        help='validate the profile and UDP listener without waiting for USB')
    args = parser.parse_args()
    if args.timeout <= 0 or args.capture_seconds <= 0 or args.max_packets <= 0:
        parser.error('timeouts and max-packets must be positive')
    if not args.capture.parent.is_dir():
        parser.error('capture directory must already exist')
    try:
        iface = validate_profile()
        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        listener.bind(('0.0.0.0', 5140))
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        parser.exit(1, f'USB log preflight failed: {error}\n')
    if args.check_only:
        print(f'USB log preflight ready profile={PROFILE} interface={iface} '
              'address=192.168.7.1/24 udp_port=5140')
        listener.close()
        return 0

    print('USER HELPER READY', flush=True)
    deadline = time.monotonic() + args.timeout
    stable_iface = None
    stable_count = 0
    while time.monotonic() < deadline:
        names = list(interfaces())
        if len(names) > 1:
            listener.close()
            parser.exit(1, 'multiple interfaces match the phone ECM MAC\n')
        if len(names) == 1 and names[0] == iface:
            if stable_iface == names[0]:
                stable_count += 1
            else:
                stable_iface, stable_count = names[0], 1
            # Wait for udev/NetworkManager to finish renaming the initial usb0.
            if stable_count >= 3:
                break
        else:
            stable_iface, stable_count = None, 0
        time.sleep(0.2)
    else:
        listener.close()
        parser.exit(1, 'expected NetworkManager USB ECM interface did not stabilize\n')
    if stable_iface:
        try:
            activate_profile(stable_iface)
        except (OSError, subprocess.SubprocessError, RuntimeError) as error:
            listener.close()
            parser.exit(1, f'USB ECM NetworkManager setup failed: {error}\n')
        iface = stable_iface
        print(f'USB ECM host ready: {iface}, 192.168.7.1/24', flush=True)

    packets = 0
    payload = bytearray()
    capture_deadline = time.monotonic() + args.capture_seconds
    while packets < args.max_packets and time.monotonic() < capture_deadline:
        ready, _, _ = select.select([listener], [], [],
                                    min(0.25, max(0, capture_deadline - time.monotonic())))
        if not ready:
            continue
        data, peer = listener.recvfrom(65535)
        if peer[0] != PHONE_IP:
            continue
        payload.extend(data)
        packets += 1
    listener.close()
    args.capture.write_bytes(payload)
    print(f'USB log capture complete packets={packets} log_bytes={len(payload)}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
