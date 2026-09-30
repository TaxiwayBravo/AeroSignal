import os
from configure import ROOT, read_env


def validate(config, page_size=None):
    errors = []
    for key, low, high in [('FEEDER_LAT', -90, 90), ('FEEDER_LONG', -180, 180), ('FEEDER_ALT_M', -500, 9000)]:
        try:
            if not low <= float(config[key]) <= high:
                raise ValueError()
        except (KeyError, ValueError):
            errors.append(f'{key} must be between {low} and {high}.')
    profiles = config.get('COMPOSE_PROFILES', '').split(',')
    for profile, fields in {'fr24': ['FR24KEY'], 'flightaware': ['FLIGHTAWARE_ID'], 'airnav': ['AIRNAV_KEY'], 'opensky': ['OPENSKY_USERNAME', 'OPENSKY_SERIAL']}.items():
        if profile in profiles:
            for field in fields:
                if not config.get(field):
                    errors.append(f'{profile} requires {field}.')
    if 'airnav' in profiles and page_size is not None and page_size != 4096:
        errors.append('AirNav requires a 4 KB page kernel. Disable AirNav or follow its upstream Pi 5 instructions in README.')
    return errors


if __name__ == '__main__':
    errors = validate(read_env(ROOT / '.env'), os.sysconf('SC_PAGE_SIZE'))
    if errors:
        raise SystemExit('\n'.join(errors))
