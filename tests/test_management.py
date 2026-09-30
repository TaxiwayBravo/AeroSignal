import copy
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from manager.settings import build_settings, public_settings, read_env, write_env
from manager.service import Controller, password_record
from manager.network import Network, validate_network, keyfile, split_fields
import server
import scripts.install_manager as install_manager

BASE = {'station': {'name': 'Test station', 'latitude': '51.5', 'longitude': '-0.1',
                    'altitude': '25', 'timezone': 'UTC', 'device': '0'},
        'enabled': ['adsblol'], 'credentials': {}}
DEVICES = [{'interface': 'eth0', 'kind': 'ethernet'}, {'interface': 'wlan0', 'kind': 'wifi'}]
NET = {'interface': 'eth0', 'kind': 'ethernet', 'method': 'auto', 'dns': ''}


class SettingsTests(unittest.TestCase):
    def test_preserve_and_mask_secret(self):
        data = copy.deepcopy(BASE)
        data['enabled'] = ['fr24', 'adsblol']
        config = build_settings({'FR24KEY': 'my-private-key'}, data)
        self.assertEqual(config['FR24KEY'], 'my-private-key')
        self.assertNotIn('my-private-key', json.dumps(public_settings(config)))
        self.assertIn('in.adsb.lol', config['ULTRAFEEDER_CONFIG'])
        self.assertEqual(config['COMPOSE_PROFILES'], 'fr24')

    def test_clear_key_requires_disabling_feeder(self):
        data = copy.deepcopy(BASE)
        data.update(enabled=['fr24'], clear_credentials=['FR24KEY'])
        with self.assertRaises(ValueError):
            build_settings({'FR24KEY': 'saved'}, data)
        data['enabled'] = []
        self.assertEqual(build_settings({'FR24KEY': 'saved'}, data)['FR24KEY'], '')

    def test_reject_invalid_input(self):
        for change in [{'enabled': ['unknown']}, {'credentials': {'PATH': 'injection'}},
                       {'station': {**BASE['station'], 'latitude': 'nan'}},
                       {'station': {**BASE['station'], 'name': 'bad\nFIELD=value'}},
                       {'station': {**BASE['station'], 'timezone': '../etc/passwd'}}]:
            with self.assertRaises(ValueError):
                build_settings({}, {**BASE, **change})

    def test_atomic_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env'
            config = build_settings({}, BASE)
            write_env(path, config)
            self.assertEqual(read_env(path), config)
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)

    def test_failed_service_apply_restores_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = Controller(tmp, password_record('test-password'))
            old = build_settings({}, BASE)
            new = {**old, 'STATION_NAME': 'New'}
            write_env(Path(tmp) / '.env', new)
            controller.apply_services = Mock(side_effect=[ValueError('failed'), None])
            controller.apply(old, new)
            self.assertEqual(read_env(Path(tmp) / '.env'), old)
            self.assertEqual(controller.job['state'], 'error')
            self.assertEqual(controller.apply_services.call_count, 2)


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth = password_record('test-password')

    def test_auth_required_and_logout(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = Controller(tmp, self.auth, preview=True)
            self.assertEqual(controller.dispatch('POST', '/settings', BASE)[0], 401)
            status, result = controller.login('test-password')
            self.assertEqual(status, 200)
            token = result['token']
            self.assertEqual(controller.dispatch('POST', '/settings', BASE, token)[0], 202)
            self.assertEqual(controller.dispatch('GET', '/settings', {}, token)[0], 200)
            controller.dispatch('POST', '/logout', {}, token)
            self.assertFalse(controller.authenticated(token))

    def test_expiration_and_rate_limit(self):
        controller = Controller('.', self.auth, preview=True)
        controller.sessions['expired'] = time.time() - 1
        self.assertFalse(controller.authenticated('expired'))
        for _ in range(5):
            self.assertEqual(controller.login('wrong')[0], 401)
        self.assertEqual(controller.login('test-password')[0], 429)

    def test_first_run_claim_is_atomic_and_one_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'admin.json'
            controller = Controller(tmp, auth_path=path, preview=True)
            session = controller.dispatch('GET', '/session', {})[1]
            self.assertTrue(session['setup_required'])
            status, result = controller.dispatch('POST', '/setup', {
                'password': 'a-secure-password', 'confirmation': 'a-secure-password'})
            self.assertEqual(status, 201)
            self.assertTrue(path.exists())
            self.assertTrue(controller.authenticated(result['token']))
            self.assertEqual(controller.dispatch('POST', '/setup', {
                'password': 'another-password', 'confirmation': 'another-password'})[0], 409)

    def test_manager_unit_allows_password_file_directory(self):
        source = Path(install_manager.__file__).read_text()
        self.assertIn('ReadWritePaths={ROOT} /etc/aerosignal ', source)

    def test_appliance_reserves_rtl_sdr_for_readsb(self):
        stage = Path(__file__).resolve().parents[1] / 'image/stage-aerosignal/00-install/01-run-chroot.sh'
        source = stage.read_text()
        self.assertIn('blacklist rtl2832_sdr', source)
        self.assertIn('blacklist dvb_usb_rtl28xxu', source)

    def test_browser_csrf_and_httponly_cookie(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = Controller(tmp, self.auth, preview=True)
            httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{httpd.server_port}'
            try:
                with patch('server.management.PREVIEW', controller):
                    headers = {'Content-Type': 'application/json', 'Origin': 'http://evil.test', 'X-AeroSignal': '1'}
                    payload = json.dumps({'password': 'test-password'}).encode()
                    with self.assertRaises(HTTPError) as error:
                        urlopen(Request(base+'/api/manage/login', payload, headers))
                    self.assertEqual(error.exception.code, 403)
                    error.exception.close()
                    headers['Origin'] = base
                    with urlopen(Request(base+'/api/manage/login', payload, headers)) as response:
                        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
                        self.assertIn('SameSite=Strict', response.headers['Set-Cookie'])
                        self.assertNotIn('token', json.load(response))
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join()


class NetworkTests(unittest.TestCase):
    def test_status_marks_connected_ethernet(self):
        network = Network()
        network.devices = lambda: [
            {'interface': 'eth0', 'kind': 'ethernet', 'state': 'connected', 'address': '192.168.1.2/24'},
            {'interface': 'wlan0', 'kind': 'wifi', 'state': 'disconnected', 'address': ''},
        ]
        with patch('manager.network.shutil.which', return_value='/usr/bin/tool'):
            self.assertTrue(network.status()['ethernet_connected'])

    def test_static_validation(self):
        valid = {**NET, 'method': 'manual', 'address': '192.168.1.50/24', 'gateway': '192.168.1.1', 'dns': '1.1.1.1, 8.8.8.8'}
        self.assertEqual(validate_network(valid, DEVICES)['dns'], '1.1.1.1;8.8.8.8')
        for change in [{'gateway': '10.0.0.1'}, {'address': 'bad'}, {'dns': 'hello'}, {'interface': 'eth0;rm'}, {'kind': 'wifi'}]:
            with self.assertRaises(ValueError):
                validate_network({**valid, **change}, DEVICES)

    def test_wifi_password_in_keyfile_not_command(self):
        settings = validate_network({**NET, 'interface': 'wlan0', 'kind': 'wifi', 'ssid': 'My Wi-Fi', 'password': 's3cret a;b', 'security': 'wpa-psk'}, DEVICES)
        content = keyfile(settings, 'test-uuid')
        self.assertIn('psk=s3cret\\sa\\;b', content)
        self.assertIn('autoconnect=false', content)
        self.assertEqual(split_fields(r'My\:WiFi:85:WPA2:wlan0')[0], 'My:WiFi')

    def test_checkpoint_precedes_mutation(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            if 'GetDeviceByIpIface' in args:
                return '{"data":["/device/1"]}'
            if 'CheckpointCreate' in args:
                return '{"data":["/checkpoint/1"]}'
            return '{"data":[]}' if args[0] == 'busctl' else ''
        with tempfile.TemporaryDirectory() as tmp, patch('manager.network.threading.Thread') as thread, patch('manager.network.threading.Timer'):
            network = Network(run, tmp)
            network.devices = lambda: DEVICES
            result = network.apply(NET)
            self.assertIn('CheckpointCreate', calls[1])
            self.assertEqual(calls[1][-2:], ['120', '2'])
            network.activate(result['id'])
            self.assertEqual(network.pending['phase'], 'awaiting_confirmation')
            self.assertTrue(any('connection' in call and 'load' in call for call in calls))
            network.confirm(result['id'])
            self.assertIsNone(network.pending)
            self.assertIn('CheckpointDestroy', calls[-1])

    def test_timeout_deletes_new_profile_and_requests_rollback(self):
        run = Mock(return_value='{"data":[]}')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'staged.nmconnection'
            path.write_text('private')
            network = Network(run, tmp)
            network.pending = {'id': 'test', 'checkpoint': '/checkpoint/1', 'profile': path}
            network.expire('test')
            self.assertFalse(path.exists())
            self.assertIsNone(network.pending)
            self.assertIn('CheckpointRollback', run.call_args_list[0].args[0])

    def test_no_profile_if_checkpoint_unavailable(self):
        run = Mock(side_effect=['{"data":["/device/1"]}', ValueError('not supported')])
        with tempfile.TemporaryDirectory() as tmp:
            network = Network(run, tmp)
            network.devices = lambda: DEVICES
            with self.assertRaises(ValueError):
                network.apply(NET)
            self.assertEqual(list(Path(tmp).iterdir()), [])
            self.assertIsNone(network.pending)


if __name__ == '__main__':
    unittest.main()
