"""AeroSignal dashboard with an authenticated bridge to Pi management."""
import json
import os
import time
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
import management
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

STATIC = Path(__file__).parent / 'static'
UPSTREAM = os.environ.get('RECEIVER_URL', 'http://ultrafeeder')


def receiver_snapshot():
    try:
        with urlopen(UPSTREAM.rstrip('/') + '/data/aircraft.json', timeout=4) as response:
            data = json.load(response)
        age = max(0, time.time() - float(data['now']))
        return {'connected': age < 30, 'age': round(age), 'aircraft': data.get('aircraft', []),
                'messages': data.get('messages', 0), 'now': data['now']}
    except (URLError, OSError, ValueError, KeyError, TypeError):
        return {'connected': False, 'age': None, 'aircraft': [], 'messages': 0, 'now': time.time()}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path.startswith('/api/manage/'):
            return self.manage('GET', path)
        if path == '/api/status':
            data = receiver_snapshot()
            data.update(station=os.environ.get('STATION_NAME', 'AeroSignal station'),
                        map_url=os.environ.get('MAP_URL', ''),
                        feeders=os.environ.get('ENABLED_FEEDERS', '').split(','), version='1.2.0')
            status, metadata = management.request('GET', '/public')
            if status == 200:
                data.update(metadata)
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == '/health':
            self.send_response(204)
            self.end_headers()
        else:
            super().do_GET()

    def json_response(self, status, body, cookie=None):
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(encoded)))
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        if not self.path.startswith('/api/manage/'):
            return self.json_response(404, {'error': 'Unknown operation.'})
        # Browser requests must be same-origin JSON with an explicit custom header.
        origin = urlsplit(self.headers.get('Origin', ''))
        if origin.scheme not in ('http', 'https') or origin.netloc != self.headers.get('Host') or self.headers.get('X-AeroSignal') != '1':
            return self.json_response(403, {'error': 'This request must come from the AeroSignal settings page.'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.json_response(415, {'error': 'JSON required.'})
        self.manage('POST', self.path)

    def manage(self, method, path):
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 <= length <= 32768:
                return self.json_response(413, {'error': 'Request too large.'})
            body = json.loads(self.rfile.read(length)) if method == 'POST' and length else {}
            if not isinstance(body, dict):
                raise ValueError()
        except (ValueError, TypeError):
            return self.json_response(400, {'error': 'Invalid JSON request.'})
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
            token = cookies['aerosignal_session'].value if 'aerosignal_session' in cookies else ''
        except Exception:
            token = ''
        status, result = management.request(method, path.removeprefix('/api/manage'), body, token)
        cookie = None
        if 'token' in result:
            cookie = f'aerosignal_session={result.pop("token")}; HttpOnly; SameSite=Strict; Path=/api/manage; Max-Age=3600'
        if path == '/api/manage/logout' and status == 200:
            cookie = 'aerosignal_session=; HttpOnly; SameSite=Strict; Path=/api/manage; Max-Age=0'
        return self.json_response(status, result, cookie)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')
        super().end_headers()


if __name__ == '__main__':
    if os.environ.get('AEROSIGNAL_PREVIEW') == '1':
        if os.environ.get('BIND', '0.0.0.0') != '127.0.0.1':
            raise SystemExit('Preview mode must bind to 127.0.0.1.')
        management.enable_preview()
    ThreadingHTTPServer((os.environ.get('BIND', '0.0.0.0'), int(os.environ.get('PORT', '8080'))), Handler).serve_forever()
