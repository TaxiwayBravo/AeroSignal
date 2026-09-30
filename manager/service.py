"""Restricted local management API over a Unix socket, never a TCP port."""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import socketserver
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler

from .network import Network
from .settings import ACCOUNT_FIELDS, build_settings, public_settings, read_env, write_env


def password_record(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    return {'salt': salt, 'digest': digest}


class Controller:
    def __init__(self, project, auth, preview=False):
        self.project = Path(project)
        self.auth = auth
        self.preview = preview
        self.sessions = {}
        self.failures = []
        self.lock = threading.RLock()
        self.job = {'state': 'idle', 'message': ''}
        self.network = Network()
        if preview:
            from .preview import PreviewNetwork
            self.network = PreviewNetwork()

    def authenticated(self, token):
        with self.lock:
            now = time.time()
            self.sessions = {k: v for k, v in self.sessions.items() if v > now}
            return bool(token and token in self.sessions)

    def login(self, password):
        with self.lock:
            now = time.time()
            self.failures = [t for t in self.failures if now - t < 300]
            if len(self.failures) >= 5:
                return 429, {'error': 'Too many attempts. Try again in five minutes.'}
            if not isinstance(password, str) or len(password) > 256:
                return 400, {'error': 'Invalid password.'}
            digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(self.auth['salt']), 600000).hex()
            if not hmac.compare_digest(digest, self.auth['digest']):
                self.failures.append(now)
                return 401, {'error': 'Incorrect administrator password.'}
            self.failures.clear()
            token = secrets.token_urlsafe(32)
            self.sessions[token] = now + 3600
            return 200, {'token': token, 'message': 'Settings unlocked for one hour.'}

    def compose(self, args, env_file=None, timeout=180):
        base = ['docker', 'compose', '--project-directory', str(self.project)]
        if env_file:
            base += ['--env-file', str(env_file)]
        result = subprocess.run(base + args, cwd=self.project, capture_output=True, timeout=timeout)
        if result.returncode:
            raise ValueError('Receiver services could not be applied. Check Docker and the station configuration on the Pi.')

    def save(self, body):
        with self.lock:
            if self.job['state'] == 'applying':
                raise ValueError('A settings change is already being applied.')
            path = self.project / '.env'
            old = read_env(path)
            new = build_settings(old, body, os.sysconf('SC_PAGE_SIZE') if hasattr(os, 'sysconf') and not self.preview else None)
            if not self.preview:
                candidate = self.project / '.env.validation'
                try:
                    write_env(candidate, new)
                    self.compose(['config', '--quiet'], candidate, timeout=30)
                finally:
                    candidate.unlink(missing_ok=True)
            write_env(path, new)
            self.job = {'state': 'applying', 'message': 'Applying receiver and feeder settings…'}
            if self.preview:
                self.job = {'state': 'success', 'message': 'Preview settings saved. No real receiver or feeder was changed.'}
            else:
                threading.Thread(target=self.apply, args=(old, new), daemon=True).start()
            return {'message': self.job['message'], 'settings': public_settings(new), 'job': dict(self.job)}

    def apply_services(self, config):
        selected = config.get('COMPOSE_PROFILES', '').split(',')
        disabled = [key for key in ACCOUNT_FIELDS if key not in selected]
        if disabled:
            self.compose([arg for key in ACCOUNT_FIELDS for arg in ('--profile', key)] + ['stop', *disabled])
        self.compose(['up', '-d', '--no-deps', 'ultrafeeder', *[key for key in selected if key]])

    def apply(self, old, new):
        try:
            self.apply_services(new)
            result = {'state': 'success', 'message': 'Configuration applied. Check each provider to verify data delivery.'}
        except (ValueError, OSError, subprocess.TimeoutExpired):
            write_env(self.project / '.env', old)
            try:
                self.apply_services(old)
                result = {'state': 'error', 'message': 'Apply failed. The previous configuration was restored.'}
            except (ValueError, OSError, subprocess.TimeoutExpired):
                result = {'state': 'error', 'message': 'Apply failed. Previous settings were restored to disk, but services need attention on the Pi.'}
        with self.lock:
            self.job = result

    def dispatch(self, method, path, body, token=''):
        if path == '/session' and method == 'GET':
            return 200, {'authenticated': self.authenticated(token), 'preview': self.preview, 'available': True}
        if path == '/login' and method == 'POST':
            return self.login(body.get('password'))
        if path == '/public' and method == 'GET':
            config = read_env(self.project / '.env')
            return 200, {'station': config.get('STATION_NAME', 'AeroSignal'),
                         'feeders': config.get('ENABLED_FEEDERS', '').split(','), 'map_url': config.get('MAP_URL', '')}
        if not self.authenticated(token):
            return 401, {'error': 'Unlock settings with the station administrator password.'}
        if path == '/logout' and method == 'POST':
            with self.lock:
                self.sessions.pop(token, None)
            return 200, {'message': 'Settings locked.'}
        if path == '/settings' and method == 'GET':
            return 200, {'settings': public_settings(read_env(self.project / '.env')), 'job': dict(self.job)}
        if path == '/settings' and method == 'POST':
            return 202, self.save(body)
        if path == '/job' and method == 'GET':
            return 200, dict(self.job)
        if path == '/network' and method == 'GET':
            return 200, self.network.status()
        if path == '/network/scan' and method == 'POST':
            return 200, {'networks': self.network.scan()}
        if path == '/network/apply' and method == 'POST':
            return 202, self.network.apply(body)
        if path == '/network/confirm' and method == 'POST':
            return 200, self.network.confirm(body.get('id'))
        if path == '/network/revert' and method == 'POST':
            return 200, self.network.rollback(body.get('id'))
        return 404, {'error': 'Unknown management operation.'}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Never log credentials, cookies or request bodies.

    def handle_request(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 <= length <= 32768:
                raise ValueError('Request too large.')
            body = json.loads(self.rfile.read(length)) if length else {}
            if not isinstance(body, dict):
                raise ValueError('Expected a JSON object.')
            status, result = self.server.controller.dispatch(self.command, self.path, body, self.headers.get('X-Session', ''))
        except (ValueError, TypeError, KeyError) as exc:
            status, result = 400, {'error': str(exc)}
        except Exception:
            status, result = 503, {'error': 'Management operation failed. Check the Pi service and try again.'}
        encoded = json.dumps(result).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    do_GET = handle_request
    do_POST = handle_request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--socket', default='/run/aerosignal/manager.sock')
    parser.add_argument('--auth', default='/etc/aerosignal/admin.json')
    args = parser.parse_args()
    controller = Controller(args.project, json.loads(Path(args.auth).read_text()))
    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True
    path = Path(args.socket)
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    server = Server(str(path), Handler)
    os.chown(path, 0, 65534)
    os.chmod(path, 0o660)
    server.controller = controller
    server.serve_forever()


if __name__ == '__main__':
    main()
