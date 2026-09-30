#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "$(uname -m)" in
  armv6l) echo 'Original Pi / Zero ARMv6: use dashboard-only mode; see README.'; exit 1 ;;
  aarch64|armv7l|x86_64) ;;
  *) echo 'Unsupported architecture for the packaged receiver stack.'; exit 1 ;;
esac
test -f .env || { echo 'Run python3 scripts/configure.py first.'; exit 1; }
test -S /run/aerosignal/manager.sock || echo 'Note: web settings are unavailable until you run: sudo python3 scripts/install_manager.py'
docker compose version >/dev/null || { echo 'Install Docker Engine with the Compose plugin; see README.'; exit 1; }
test -d /dev/bus/usb || { echo 'No USB bus found. Attach your RTL-SDR.'; exit 1; }
docker compose config --quiet
# Remove optional feeders which the user deselected in the wizard.
python3 scripts/validate_config.py
docker compose --profile fr24 --profile flightaware --profile airnav --profile opensky stop fr24 flightaware airnav opensky
docker compose up -d --build --remove-orphans
echo 'Dashboard: http://<pi-ip>:8080 · tar1090: http://<pi-ip>:8081'
docker compose ps
