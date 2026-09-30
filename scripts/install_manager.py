"""Install the local management service on the Pi; run with sudo."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reset-password', action='store_true')
    parser.add_argument('--no-start', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not hasattr(os, 'geteuid') or os.geteuid() != 0:
        raise SystemExit('Run on the Pi: sudo python3 scripts/install_manager.py')
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(ROOT)):
        raise SystemExit('Use a project path containing only letters, digits, dots, slashes, dashes and underscores.')
    for program in ('nmcli', 'busctl', 'docker', 'systemctl'):
        if not shutil.which(program):
            raise SystemExit(f'{program} is missing. Install Docker and use Raspberry Pi OS with NetworkManager first.')
    config_dir = Path('/etc/aerosignal')
    config_dir.mkdir(mode=0o700, exist_ok=True)
    auth_path = config_dir / 'admin.json'
    if args.reset_password:
        auth_path.unlink(missing_ok=True)
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
    subprocess.run(['systemctl', 'enable', 'aerosignal-manager.service'], check=True)
    if not args.no_start:
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'restart', 'aerosignal-manager.service'], check=True)
    print('Management installed. Open AeroSignal in a browser to create the administrator password.')


if __name__ == '__main__':
    main()
