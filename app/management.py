"""Same-origin bridge to the host's restricted Unix-socket manager."""
import http.client
import json
import os
from pathlib import Path
import socket
import sys

SOCKET = os.environ.get('MANAGER_SOCKET', '/run/aerosignal/manager.sock')
PREVIEW = None


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        if not hasattr(socket, 'AF_UNIX'):
            raise OSError('Unix sockets require Linux.')
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET)


def request(method, path, body=None, token=''):
    if PREVIEW:
        try:
            return PREVIEW.dispatch(method, path, body or {}, token)
        except (ValueError, TypeError, KeyError) as exc:
            return 400, {'error': str(exc)}
    connection = UnixConnection('localhost', timeout=55)
    try:
        payload = json.dumps(body) if body is not None else None
        connection.request(method, path, payload, {'Content-Type': 'application/json', 'X-Session': token})
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    except (OSError, ValueError, http.client.HTTPException):
        return 503, {'available': False, 'authenticated': False,
                     'error': 'Pi management service is not installed. Run sudo python3 scripts/install_manager.py on the Pi, then restart the dashboard.'}
    finally:
        connection.close()


def enable_preview():
    global PREVIEW
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from manager.service import Controller, password_record
    from manager.settings import write_env
    root = Path(__file__).resolve().parents[1] / '.preview'
    root.mkdir(exist_ok=True)
    if not (root / '.env').exists():
        write_env(root / '.env', {'STATION_NAME': 'My AeroSignal', 'FEEDER_LAT': '51.5', 'FEEDER_LONG': '-0.1',
                                 'FEEDER_ALT_M': '25', 'TZ': 'Europe/London', 'SDR_DEVICE': '0'})
    PREVIEW = Controller(root, password_record('preview-only'), preview=True)
