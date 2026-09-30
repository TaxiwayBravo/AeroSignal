import io
import json
import sys
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import urlopen

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / p) for p in ('app', 'scripts')]
import server
from configure import safe
from validate_config import validate


class ReceiverTests(unittest.TestCase):
    def test_map_is_proxied_on_dashboard_origin(self):
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Type': 'text/html', 'Cache-Control': 'max-age=10'}
            def __enter__(self):
                return self
            def __exit__(self, *_):
                self.close()

        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with patch('server.urlopen', return_value=Response(b'<html><head></head><body>tar1090</body></html>')):
                with urlopen(f'http://127.0.0.1:{httpd.server_port}/map/') as response:
                    body = response.read()
                    self.assertIn(b'<base href="/map/">', body)
                    self.assertEqual(response.headers['X-Frame-Options'], 'SAMEORIGIN')
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()

    def test_http_api_and_static_isolation(self):
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{httpd.server_port}'
        try:
            with patch('server.receiver_snapshot', return_value={'connected': True, 'aircraft': [], 'messages': 1, 'now': time.time(), 'age': 0}):
                with urlopen(base + '/api/status') as response:
                    data = json.load(response)
                    self.assertTrue(data['connected'])
                    self.assertNotIn('FR24KEY', data)
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
            with urlopen(base + '/') as response:
                self.assertIn(b'AeroSignal', response.read())
            with urlopen(base + '/logo.png') as response:
                self.assertEqual(response.read(8), b'\x89PNG\r\n\x1a\n')
            with self.assertRaises(URLError) as error:
                urlopen(base + '/.env')
            error.exception.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()

    def test_fresh_receiver(self):
        data = {'now': time.time(), 'messages': 123, 'aircraft': [{'hex': 'abcdef'}]}
        with patch('server.urlopen', return_value=io.BytesIO(json.dumps(data).encode())):
            result = server.receiver_snapshot()
        self.assertTrue(result['connected'])
        self.assertEqual(result['aircraft'][0]['hex'], 'abcdef')

    def test_stale_is_not_live(self):
        with patch('server.urlopen', return_value=io.BytesIO(json.dumps({'now': time.time()-60}).encode())):
            self.assertFalse(server.receiver_snapshot()['connected'])

    def test_offline(self):
        with patch('server.urlopen', side_effect=URLError('offline')):
            result = server.receiver_snapshot()
        self.assertFalse(result['connected'])
        self.assertEqual(result['aircraft'], [])

    def test_invalid_json(self):
        with patch('server.urlopen', return_value=io.BytesIO(b'<html>bad gateway</html>')):
            self.assertFalse(server.receiver_snapshot()['connected'])

    def test_env_injection(self):
        for value in ['a\nB=1', '${SECRET}', 'test#comment', 'a"b']:
            with self.assertRaises(ValueError):
                safe(value)

    def test_validation(self):
        base = {'FEEDER_LAT': '51', 'FEEDER_LONG': '-1', 'FEEDER_ALT_M': '20'}
        self.assertEqual(validate(base), [])
        self.assertTrue(validate(dict(base, FEEDER_LAT='nan')))
        self.assertTrue(validate(dict(base, COMPOSE_PROFILES='fr24')))
        self.assertTrue(validate(dict(base, COMPOSE_PROFILES='airnav', AIRNAV_KEY='x'), 16384))


if __name__ == '__main__':
    unittest.main()
