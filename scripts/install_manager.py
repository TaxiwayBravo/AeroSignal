"""Install the local management service on the Pi; run with sudo."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from manager.service import password_record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--keep-password', action='store_true')
    parser.add_argument('--reset-password', action='store_true')
    args = parser.parse_args()
    if not hasattr(os, 'geteuid') or os.geteuid() != 0:
        raise SystemExit('Run on the Pi: sudo python3 scripts/install_manager.py')
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(ROOT)):
        raise SystemExit('Use a project path containing only letters, digits, dots, slashes, dashes and underscores.')
    for program in ('nmcli', 'busctl', 'docker', 'systemctl'):
        if not shutil.which(program):
            raise SystemExit(f'{program} is missing. Install Docker and use Raspberry Pi OS with NetworkManager first.')
    if not (ROOT / '.env').exists():
        raise SystemExit('Run python3 scripts/configure.py once to configure the receiver, then install management.')
    config_dir = Path('/etc/aerosignal')
    config_dir.mkdir(mode=0o700, exist_ok=True)
    auth_path = config_dir / 'admin.json'
    if args.keep_password and not auth_path.exists():
        raise SystemExit('No administrator password exists. Run installer without --keep-password.')
    if not auth_path.exists() or args.reset_password:
        password = getpass.getpass('Create administrator password (at least 12 characters): ')
        if len(password) < 12 or len(password) > 256:
            raise SystemExit('Use 12–256 characters.')
        if password != getpass.getpass('Repeat password: '):
            raise SystemExit('Passwords did not match.')
        fd = os.open(auth_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(password_record(password), stream)
        auth_path.chmod(0o600)
    destination = Path('/opt/aerosignal-manager')
    for directory in ('manager', 'scripts'):
        target = destination / directory
        target.mkdir(parents=True, exist_ok=True)
        for source in (ROOT / directory).glob('*.py'):
            shutil.copyfile(source, target / source.name)
            (target / source.name).chmod(0o644)
    unit = f'''[Unit]
Description=AeroSignal station management
After=NetworkManager.service docker.service
Wants=NetworkManager.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aerosignal-manager
ExecStart=/usr/bin/python3 -m manager.service --project {ROOT}
Restart=on-failure
RuntimeDirectory=aerosignal
RuntimeDirectoryMode=0755
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={ROOT} /etc/NetworkManager/system-connections /run/aerosignal
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

[Install]
WantedBy=multi-user.target
'''
    Path('/etc/systemd/system/aerosignal-manager.service').write_text(unit)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', 'aerosignal-manager.service'], check=True)
    subprocess.run(['systemctl', 'restart', 'aerosignal-manager.service'], check=True)
    print('Management installed. Run bash scripts/start.sh, then use Unlock settings in AeroSignal.')


if __name__ == '__main__':
    main()
