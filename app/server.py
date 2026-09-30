"""AeroSignal local, read-only dashboard. Python standard library only."""
import json
import os
import time
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
        if path == '/api/status':
            data = receiver_snapshot()
            data.update(station=os.environ.get('STATION_NAME', 'AeroSignal station'),
                        map_url=os.environ.get('MAP_URL', ''),
                        feeders=os.environ.get('ENABLED_FEEDERS', '').split(','), version='1.0.0')
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

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()


if __name__ == '__main__':
    ThreadingHTTPServer((os.environ.get('BIND', '0.0.0.0'), int(os.environ.get('PORT', '8080'))), Handler).serve_forever()
