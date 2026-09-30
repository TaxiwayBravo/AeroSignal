"""Validated feeder configuration and private, atomic persistence."""
import os
from pathlib import Path
import sys
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from configure import COMMUNITY, read_env, safe
from validate_config import validate

ACCOUNT_FIELDS = {
    'fr24': ['FR24KEY'], 'flightaware': ['FLIGHTAWARE_ID'],
    'airnav': ['AIRNAV_KEY'], 'opensky': ['OPENSKY_USERNAME', 'OPENSKY_SERIAL'],
}
CREDENTIALS = [field for fields in ACCOUNT_FIELDS.values() for field in fields]
FIELDS = {'name': 'STATION_NAME', 'latitude': 'FEEDER_LAT', 'longitude': 'FEEDER_LONG',
          'altitude': 'FEEDER_ALT_M', 'timezone': 'TZ', 'device': 'SDR_DEVICE'}


def public_settings(config):
    return {'station': {k: config.get(v, '') for k, v in FIELDS.items()},
            'enabled': [x for x in config.get('ENABLED_FEEDERS', '').split(',') if x],
            'credentials': {k: bool(config.get(k)) for k in CREDENTIALS}}


def build_settings(old, body, page_size=None):
    if not isinstance(body, dict) or not isinstance(body.get('station'), dict):
        raise ValueError('Station settings are required.')
    enabled = body.get('enabled')
    if not isinstance(enabled, list) or any(not isinstance(x, str) or x not in {*COMMUNITY, *ACCOUNT_FIELDS} for x in enabled):
        raise ValueError('Choose only supported feeders.')
    config = dict(old)
    for field, key in FIELDS.items():
        value = str(body['station'].get(field, '')).strip()
        if not value or len(value) > 100:
            raise ValueError(f'{field.capitalize()} is required (maximum 100 characters).')
        config[key] = safe(value)
    if config['TZ'] != 'UTC':
        try:
            ZoneInfo(config['TZ'])
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Enter a valid timezone, for example Europe/London.')
    updates = body.get('credentials', {})
    clears = body.get('clear_credentials', [])
    if not isinstance(updates, dict) or not isinstance(clears, list):
        raise ValueError('Invalid credentials.')
    if any(k not in CREDENTIALS for k in [*updates, *clears]):
        raise ValueError('Unknown credential field.')
    for key in clears:
        config[key] = ''
    for key, value in updates.items():
        if not isinstance(value, str) or len(value) > 256:
            raise ValueError('Credential is too long.')
        if value.strip():
            config[key] = safe(value.strip())
    enabled = list(dict.fromkeys(enabled))
    config['FEEDER_UUID'] = config.get('FEEDER_UUID') or str(uuid.uuid4())
    config['ENABLED_FEEDERS'] = ','.join(enabled)
    config['COMPOSE_PROFILES'] = ','.join(k for k in enabled if k in ACCOUNT_FIELDS)
    connections = []
    for key in enabled:
        if key in COMMUNITY:
            _, host, port = COMMUNITY[key]
            suffix = f',uuid={config["FEEDER_UUID"]}' if key == 'adsbx' else ''
            connections.append(f'adsb,{host},{port},beast_reduce_plus_out{suffix}')
    config['ULTRAFEEDER_CONFIG'] = ';'.join(connections)
    errors = validate(config, page_size)
    if errors:
        raise ValueError(' '.join(errors))
    return config


def write_env(path, config):
    path = Path(path)
    original = path.stat() if path.exists() else None
    temporary = path.parent / ('.env.' + uuid.uuid4().hex)
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write('\n'.join(f'{k}={safe(v)}' for k, v in config.items()) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        if original and hasattr(os, 'chown'):
            os.chown(temporary, original.st_uid, original.st_gid)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
