#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" = 0 || { echo 'Run with sudo.'; exit 1; }
cat > /etc/modprobe.d/aerosignal-rtlsdr.conf <<'EOF'
# Reserve RTL-SDR for ADS-B reception rather than DVB television.
blacklist rtl2832
blacklist rtl2832_sdr
blacklist dvb_usb_rtl28xxu
EOF
echo 'RTL-SDR TV drivers blacklisted. Reboot the Pi before starting AeroSignal.'
