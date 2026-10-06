"""Create a temporary setup hotspot when the appliance has no wired connection."""
import shutil
import subprocess
import time
import uuid
from pathlib import Path


def run(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=45)


def uplink_online():
    result = run(['nmcli', '-t', '-f', 'TYPE,STATE,CONNECTION', 'device', 'status'])
    return result.returncode == 0 and any(
        (line.startswith('ethernet:connected:') or line.startswith('wifi:connected:')) and
        not line.endswith(':AeroSignal-Setup') for line in result.stdout.splitlines())


def main():
    if not shutil.which('nmcli'):
        raise SystemExit('NetworkManager is required.')
    run(['rfkill', 'unblock', 'wifi'])
    radio = run(['nmcli', 'radio', 'wifi', 'on'])
    if radio.returncode:
        raise SystemExit('Could not enable the Wi-Fi radio: ' + radio.stderr.strip())
    for _ in range(20):
        if uplink_online():
            ensure_receiver_defaults()
            return
        time.sleep(1)
    wifi = run(['nmcli', '-t', '-f', 'DEVICE,TYPE', 'device', 'status'])
    interfaces = [line.split(':', 1)[0] for line in wifi.stdout.splitlines() if line.endswith(':wifi')]
    if not interfaces:
        ensure_receiver_defaults()
        return
    # This temporary password is public by design and only provides transport to
    # the one-time claim page. The owner creates the real admin password there.
    result = run(['nmcli', 'device', 'wifi', 'hotspot', 'ifname', interfaces[0], 'con-name',
                  'AeroSignal-Setup', 'ssid', 'AeroSignal-Setup', 'password', 'aerosignal'])
    if result.returncode:
        raise SystemExit('Could not create the setup hotspot: ' + result.stderr.strip())
    ensure_receiver_defaults()


def ensure_receiver_defaults():
    """Make the receiver bootable before the web wizard is completed."""
    path = Path('/opt/aerosignal/.env')
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    existing = {}
    if path.exists():
        existing = {line.split('=', 1)[0]: line for line in path.read_text().splitlines()
                    if '=' in line and not line.startswith('#')}
    defaults = {
        'STATION_NAME': 'AeroSignal', 'FEEDER_LAT': '0', 'FEEDER_LONG': '0',
        'FEEDER_ALT_M': '0', 'SDR_DEVICE': '0', 'TZ': 'Europe/London',
        'FEEDER_UUID': str(uuid.uuid4()), 'ENABLED_FEEDERS': '', 'COMPOSE_PROFILES': ''}
    lines = [existing.get(key, f'{key}={value}') for key, value in defaults.items()]
    path.write_text('\n'.join(lines) + '\n')
    path.chmod(0o600)


if __name__ == '__main__':
    main()
