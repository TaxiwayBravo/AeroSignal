#!/bin/bash -e
systemctl enable NetworkManager
systemctl enable docker
systemctl enable avahi-daemon
# The build-time account prevents Raspberry Pi OS from launching its console
# user wizard. Lock it before export; appliance administration happens on web.
passwd --lock aerosignal
cd /opt/aerosignal
python3 scripts/install_manager.py --no-start
install -m 0644 image/aerosignal-dashboard.service /etc/systemd/system/aerosignal-dashboard.service
install -m 0644 image/aerosignal-firstboot.service /etc/systemd/system/aerosignal-firstboot.service
systemctl enable aerosignal-dashboard.service
systemctl enable aerosignal-firstboot.service
touch .env
chmod 600 .env
