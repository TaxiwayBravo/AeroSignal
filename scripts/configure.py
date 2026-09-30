"""Interactive local configuration. Never execute configuration as shell code."""
import getpass
import os
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[1]
COMMUNITY = {
    'adsbfi': ('ADS-B.fi', 'feed.adsb.fi', 30004),
    'adsblol': ('ADSB.lol', 'in.adsb.lol', 30004),
    'airplanes': ('Airplanes.live', 'feed.airplanes.live', 30004),
    'planespotters': ('Planespotters', 'feed.planespotters.net', 30004),
    'airtraffic': ('The Air Traffic', 'feed.theairtraffic.com', 30004),
    'adsbx': ('ADS-B Exchange', 'feed1.adsbexchange.com', 30004),
    'avdelphi': ('AvDelphi', 'data.avdelphi.com', 24999),
    'hpradar': ('RadarPlane', 'skyfeed.hpradar.com', 30004),
    'flyitaly': ('Fly Italy ADS-B', 'dati.flyitalyadsb.com', 4905),
}


def read_env(path):
    if not path.exists():
        return {}
    return dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines() if line and not line.startswith('#') and '=' in line)


def safe(value):
    if any(c in value for c in '\n\r\x00$\'"#'):
        raise ValueError('Use plain text without quotes, dollar signs, or # characters.')
    return value


def ask(label, default='', secret=False):
    prompt = f'{label}' + (' [saved]' if secret and default else f' [{default}]' if default else '') + ': '
    return safe((getpass.getpass(prompt) if secret else input(prompt)).strip() or default)


def number(label, default, low, high):
    while True:
        raw = ask(label, default)
        try:
            value = float(raw)
            if low <= value <= high:
                return str(value)
        except ValueError:
            pass
        print(f'Enter a number from {low} to {high}.')


def main():
    path = ROOT / '.env'
    old = read_env(path)
    selected = old.get('ENABLED_FEEDERS', '').split(',')
    config = dict(old)
    print('AeroSignal setup · Sharing is optional. Location must be the actual antenna location.')
    config['STATION_NAME'] = ask('Station name', old.get('STATION_NAME', 'AeroSignal'))
    config['FEEDER_LAT'] = number('Antenna latitude', old.get('FEEDER_LAT', ''), -90, 90)
    config['FEEDER_LONG'] = number('Antenna longitude', old.get('FEEDER_LONG', ''), -180, 180)
    config['FEEDER_ALT_M'] = number('Antenna altitude above sea level (metres)', old.get('FEEDER_ALT_M', ''), -500, 9000)
    config['TZ'] = ask('Timezone', old.get('TZ', 'Europe/London'))
    config['SDR_DEVICE'] = ask('RTL-SDR device index or serial', old.get('SDR_DEVICE', '0'))
    config['FEEDER_UUID'] = old.get('FEEDER_UUID') or str(uuid.uuid4())
    config['MAP_URL'] = old.get('MAP_URL', '')
    config['BIND_IP'] = old.get('BIND_IP', '0.0.0.0')
    enabled, connections, profiles = [], [], []
    for key, (name, host, port) in COMMUNITY.items():
        if ask(f'Share ADS-B data with {name}? y/n', 'y' if key in selected else 'n').lower() == 'y':
            enabled.append(key)
            suffix = f',uuid={config["FEEDER_UUID"]}' if key == 'adsbx' else ''
            connections.append(f'adsb,{host},{port},beast_reduce_plus_out{suffix}')
    for key, name, field in [('fr24', 'Flightradar24', 'FR24KEY'), ('flightaware', 'FlightAware', 'FLIGHTAWARE_ID'), ('airnav', 'AirNav Radar', 'AIRNAV_KEY'), ('opensky', 'OpenSky Network', 'OPENSKY_SERIAL')]:
        if ask(f'Enable {name}? y/n', 'y' if key in selected else 'n').lower() == 'y':
            value = ask(f'{name} feeder key / ID (see README)', old.get(field, ''), secret=True)
            if not value:
                print(f'{name} skipped: a feeder identity is required.')
                continue
            config[field] = value
            if key == 'opensky':
                config['OPENSKY_USERNAME'] = ask('OpenSky username', old.get('OPENSKY_USERNAME', ''))
                if not config['OPENSKY_USERNAME']:
                    print('OpenSky skipped: username required.')
                    continue
            enabled.append(key)
            profiles.append(key)
    config['ENABLED_FEEDERS'] = ','.join(enabled)
    config['COMPOSE_PROFILES'] = ','.join(profiles)
    config['ULTRAFEEDER_CONFIG'] = ';'.join(connections)
    config.setdefault('FR24KEY', '')
    config.setdefault('FLIGHTAWARE_ID', '')
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(f'{k}={safe(v)}' for k, v in config.items()) + '\n')
    temporary.replace(path)
    path.chmod(0o600)
    print('Saved .env privately. Run: bash scripts/start.sh')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled; configuration unchanged.')
