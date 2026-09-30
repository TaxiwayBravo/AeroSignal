"""NetworkManager adapter. No shell execution, no secrets in command arguments."""
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid


def command(args, timeout=25):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                                env={**os.environ, 'LC_ALL': 'C'})
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('System command unavailable or timed out. Check the Pi service logs.')
    if result.returncode:
        # Do not reflect diagnostics which might contain credentials or location.
        raise ValueError('NetworkManager could not complete the operation. Check the interface and settings.')
    return result.stdout.strip()


def split_fields(line):
    return [re.sub(r'\\(.)', r'\1', x) for x in re.split(r'(?<!\\):', line)]


def validate_network(body, devices):
    if not isinstance(body, dict):
        raise ValueError('Network settings are required.')
    result = {k: body.get(k, '') for k in ('interface', 'kind', 'method', 'address', 'gateway', 'dns', 'ssid', 'password', 'security')}
    if any(not isinstance(v, str) or '\x00' in v or '\n' in v or '\r' in v for v in result.values()):
        raise ValueError('Invalid network field.')
    if not any(d['interface'] == result['interface'] and d['kind'] == result['kind'] for d in devices):
        raise ValueError('Choose an available Wi-Fi or Ethernet interface.')
    if result['method'] not in ('auto', 'manual'):
        raise ValueError('Choose DHCP or static IPv4.')
    if result['method'] == 'manual':
        try:
            address = ipaddress.IPv4Interface(result['address'])
            gateway = ipaddress.IPv4Address(result['gateway']) if result['gateway'] else None
            if gateway and gateway not in address.network:
                raise ValueError()
            if address.ip.is_multicast or address.ip.is_unspecified or address.ip.is_loopback:
                raise ValueError()
        except ValueError:
            raise ValueError('Enter a valid IPv4 address with prefix (e.g. 192.168.1.50/24) and a gateway in that subnet.')
    dns = [v.strip() for v in result['dns'].replace(',', ' ').split()]
    try:
        for value in dns:
            ipaddress.IPv4Address(value)
    except ValueError:
        raise ValueError('DNS servers must be IPv4 addresses separated by commas.')
    if len(dns) > 3:
        raise ValueError('Use at most three DNS servers.')
    result['dns'] = ';'.join(dns)
    if result['kind'] == 'wifi':
        if not 1 <= len(result['ssid'].encode()) <= 32:
            raise ValueError('Wi-Fi name must contain 1–32 bytes.')
        if result['security'] not in ('wpa-psk', 'sae', 'open'):
            raise ValueError('Choose WPA2/WPA3 Personal, WPA3 Personal, or open Wi-Fi.')
        if result['security'] != 'open' and not 8 <= len(result['password']) <= 63:
            raise ValueError('Wi-Fi password must contain 8–63 characters.')
    result['hidden'] = body.get('hidden') is True
    return result


def escape(value):
    return value.replace('\\', '\\\\').replace(' ', '\\s').replace(';', '\\;')


def keyfile(settings, identity):
    kind = 'wifi' if settings['kind'] == 'wifi' else 'ethernet'
    lines = ['[connection]', f'id=AeroSignal {kind}', f'uuid={identity}', f'type={kind}',
             f'interface-name={settings["interface"]}', 'autoconnect=false', 'autoconnect-priority=999', '']
    if kind == 'wifi':
        lines += ['[wifi]', 'mode=infrastructure', f'ssid={escape(settings["ssid"])}', f'hidden={str(settings["hidden"]).lower()}', '']
        if settings['security'] != 'open':
            lines += ['[wifi-security]', f'key-mgmt={settings["security"]}', f'psk={escape(settings["password"])}', '']
    lines += ['[ipv4]', f'method={settings["method"]}']
    if settings['method'] == 'manual':
        lines += [f'address1={settings["address"]},{settings["gateway"]}']
    if settings['dns']:
        lines += [f'dns={settings["dns"]};', 'ignore-auto-dns=true']
    return '\n'.join(lines + ['', '[ipv6]', 'method=auto', ''])


class Network:
    def __init__(self, run=command, profile_dir='/etc/NetworkManager/system-connections'):
        self.run = run
        self.profile_dir = Path(profile_dir)
        self.lock = threading.RLock()
        self.pending = None
        self.last_result = ''

    def dbus(self, method, signature, *args):
        raw = self.run(['busctl', '--system', '--json=short', 'call', 'org.freedesktop.NetworkManager',
                        '/org/freedesktop/NetworkManager', 'org.freedesktop.NetworkManager', method,
                        signature, *map(str, args)])
        return json.loads(raw).get('data', [])

    def devices(self):
        rows = self.run(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device', 'status'])
        devices = []
        for line in rows.splitlines():
            fields = split_fields(line)
            if len(fields) != 4 or fields[1] not in ('wifi', 'ethernet') or fields[2] == 'unmanaged':
                continue
            interface, kind, state, connection = fields
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,15}', interface):
                continue
            details = self.run(['nmcli', '-t', '-f', 'IP4.ADDRESS,IP4.GATEWAY,IP4.DNS', 'device', 'show', interface])
            values = {}
            for entry in details.splitlines():
                parts = split_fields(entry)
                if len(parts) >= 2:
                    values.setdefault(parts[0].split('[')[0], []).append(':'.join(parts[1:]))
            devices.append({'interface': interface, 'kind': kind, 'state': state, 'connection': connection,
                            'address': ', '.join(values.get('IP4.ADDRESS', [])),
                            'gateway': ', '.join(values.get('IP4.GATEWAY', [])),
                            'dns': ', '.join(values.get('IP4.DNS', []))})
        return devices

    def status(self):
        if not shutil.which('nmcli') or not shutil.which('busctl'):
            return {'available': False, 'devices': [], 'pending': None, 'message': 'Network settings require NetworkManager on the Raspberry Pi.'}
        with self.lock:
            pending = None if not self.pending else {k: self.pending[k] for k in ('id', 'deadline', 'interface', 'phase')}
        devices = self.devices()
        ethernet_connected = any(d['kind'] == 'ethernet' and d['address'] and
                                 d['state'].startswith('connected') for d in devices)
        return {'available': True, 'devices': devices, 'ethernet_connected': ethernet_connected,
                'pending': pending, 'message': self.last_result}

    def scan(self):
        rows = self.run(['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY,DEVICE', 'device', 'wifi', 'list', '--rescan', 'yes'], timeout=35)
        networks = {}
        for line in rows.splitlines():
            parts = split_fields(line)
            if len(parts) == 4 and parts[0]:
                ssid, signal, security, interface = parts
                item = {'ssid': ssid, 'signal': int(signal) if signal.isdigit() else 0, 'security': security, 'interface': interface}
                key = (ssid, interface)
                if key not in networks or networks[key]['signal'] < item['signal']:
                    networks[key] = item
        return sorted(networks.values(), key=lambda n: -n['signal'])

    def apply(self, body):
        settings = validate_network(body, self.devices())
        with self.lock:
            if self.pending:
                raise ValueError('Confirm or revert the pending network change first.')
            device = self.dbus('GetDeviceByIpIface', 's', settings['interface'])[0]
            checkpoint = self.dbus('CheckpointCreate', 'aouu', 1, device, 120, 2)[0]
            identity = str(uuid.uuid4())
            profile = self.profile_dir / f'aerosignal-{identity}.nmconnection'
            self.pending = {'id': identity, 'deadline': time.time() + 120, 'interface': settings['interface'],
                            'phase': 'applying', 'checkpoint': checkpoint, 'profile': profile}
            try:
                fd = os.open(profile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    stream.write(keyfile(settings, identity))
            except Exception:
                self.rollback(identity)
                raise
            # NetworkManager owns the timeout; it survives a dashboard/service failure.
            threading.Thread(target=self.activate, args=(identity,), daemon=True).start()
            threading.Timer(122, self.expire, args=(identity,)).start()
            return {'id': identity, 'deadline': self.pending['deadline'], 'message': 'Applying network settings. Reconnect and confirm within two minutes.'}

    def activate(self, identity):
        try:
            with self.lock:
                current = dict(self.pending or {})
            if current.get('id') != identity:
                return
            self.run(['nmcli', 'connection', 'load', str(current['profile'])])
            self.run(['nmcli', '--wait', '40', 'connection', 'up', 'uuid', identity], timeout=45)
            with self.lock:
                if self.pending and self.pending['id'] == identity:
                    self.pending['phase'] = 'awaiting_confirmation'
        except ValueError:
            with self.lock:
                self.rollback(identity)
                self.last_result = 'Connection failed; previous network settings were requested for restoration.'

    def confirm(self, identity):
        with self.lock:
            p = self.pending
            if not p or p['id'] != identity or p['phase'] != 'awaiting_confirmation' or time.time() >= p['deadline'] - 5:
                raise ValueError('No network change is ready to confirm, or its confirmation window expired.')
            try:
                self.run(['nmcli', 'connection', 'modify', 'uuid', identity, 'connection.autoconnect', 'yes'])
                self.dbus('CheckpointDestroy', 'o', p['checkpoint'])
            except ValueError:
                self.rollback(identity)
                raise
            self.pending = None
            self.last_result = 'Network settings confirmed and saved.'
            return {'message': self.last_result}

    def rollback(self, identity):
        with self.lock:
            p = self.pending
            if not p or p['id'] != identity:
                raise ValueError('No matching pending network change.')
            try:
                self.dbus('CheckpointRollback', 'o', p['checkpoint'])
            except ValueError:
                pass  # The NetworkManager timeout may already have restored it.
            try:
                self.run(['nmcli', 'connection', 'delete', 'uuid', identity])
            except ValueError:
                pass
            p['profile'].unlink(missing_ok=True)
            self.pending = None
            self.last_result = 'Network change reverted. Check the interface status below.'
            return {'message': self.last_result}

    def expire(self, identity):
        with self.lock:
            if self.pending and self.pending['id'] == identity:
                self.rollback(identity)
