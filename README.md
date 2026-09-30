# AeroSignal

A local Raspberry Pi ADS-B station console with searchable live traffic, tar1090, receiver graphs, editable feeder settings for 13 platforms, and Wi-Fi/Ethernet management. The dashboard and its password-protected management service use the Python standard library; the radio software runs in SDR-Enthusiasts containers.

The primary distribution is a compressed Raspberry Pi OS image for Raspberry Pi Imager. It boots as a headless appliance: connect Ethernet, or join the temporary `AeroSignal-Setup` Wi-Fi hotspot using password `aerosignal`, then open the dashboard. The first page requires the owner to create the station administrator password. No display or SSH session is required.

Internet is required after network setup to download the receiver and feeder containers. An RTL-SDR and a 1090 MHz antenna are required for local reception. No provider accounts or keys are included. No feeds are enabled until you select them.

## Hardware support

| Hardware | Mode |
|---|---|
| Pi 3, 4, 5, 400, 500, Zero 2 W, compatible Compute Modules | Full stack on supported ARM64 Linux; 64-bit Raspberry Pi OS Lite preferred |
| Pi 2 / ARMv7 Linux | Conditional full-stack support: requires compatible Docker and upstream ARMv7 images; 32-bit Docker support is being phased out |
| Original Pi, Pi 1, Zero, Zero W / ARMv6 | Dashboard-only Python mode connected to another receiver; the bundled container stack is not supported |
| Pico / Pico W | Not supported: these are microcontrollers, not Linux computers |

The dashboard can run on Linux Pis with Python 3.9+. This does **not** mean every Pi can decode and feed every platform. On 512 MB boards, start with local reception and one feed; monitor RAM, temperature, storage, and dropped samples. Pi 4/5 with at least 2 GB RAM is the recommended complete-station target. No physical Pi has been tested as part of this build.

AirNav's binary requires a 4 KB page kernel. Some Pi 5 systems use 16 KB pages. The startup script checks this when AirNav is selected; see the [upstream explanation](https://github.com/sdr-enthusiasts/docker-airnavradar#using-the-container-on-a-raspberry-pi-5) before changing your OS kernel configuration. Other feeds can be used without AirNav.

## Install with Raspberry Pi Imager

1. Download the `AeroSignal-*.img.xz` artifact from the GitHub **Build Raspberry Pi image** workflow.
2. In Raspberry Pi Imager choose **Use custom**, select that file and write it to the SD card. The image defaults to the GB Wi-Fi regulatory domain; setting your own country in Imager is recommended outside the United Kingdom. OS customisation and SSH are optional.
3. Insert the card, attach the RTL-SDR and antenna, then power on the Pi. AeroSignal does not ask for an operating-system username; its build-time account is locked and SSH is disabled.
4. With Ethernet connected, open `http://aerosignal.local:8080` from the same network. The image sets its hostname to `aerosignal`; if `.local` discovery is unavailable on your computer, use the IP address shown by your router or the Pi's console. AeroSignal detects the wired address, hides Wi-Fi settings, and asks for the administrator password.
5. Without Ethernet, join `AeroSignal-Setup` with password `aerosignal`, open `http://10.42.0.1:8080`, create the administrator password, then select the home Wi-Fi network. Reconnect at `http://aerosignal.local:8080` after the Pi joins it.

The setup hotspot password is intentionally public and only protects the temporary link. Create the administrator password immediately. The claim endpoint closes after that password is saved. Keep AeroSignal on a trusted home network and do not forward its ports from the router.

Connect the RTL-SDR to the Zero 2 W's **USB/data** port through a data-capable OTG adapter or powered hub, not the `PWR IN` connector. The appliance image reserves supported RTL-SDR devices for readsb by blacklisting the conflicting DVB television drivers before first boot.

## Manual installation on Raspberry Pi OS

1. Install Raspberry Pi OS Lite, connect it to your network, enable SSH if needed, and attach the RTL-SDR and antenna. Use a reliable power supply and a 16 GB or larger storage device.
2. Install Python, Git, and unzip: `sudo apt update && sudo apt install -y python3 git unzip`.
3. Install Docker Engine and the Compose plugin using [Docker's Debian instructions for 64-bit Pi OS](https://docs.docker.com/engine/install/debian/) or its [32-bit Pi OS instructions](https://docs.docker.com/engine/install/raspberry-pi-os/). Docker documents declining 32-bit support; prefer 64-bit where the hardware supports it. Ensure `docker compose version` works for your user. Docker group membership grants root-equivalent control; alternatively run the Docker scripts with sudo.
4. Copy `aerosignal-1.1.0.zip` to the Pi, then run:

```bash
unzip aerosignal-1.1.0.zip
cd aerosignal
sudo bash scripts/prepare-usb.sh
sudo reboot
```

The USB preparation reserves the RTL-SDR for radio reception instead of TV reception. After reboot, return to the extracted directory:

```bash
cd aerosignal
python3 scripts/configure.py
sudo python3 scripts/install_manager.py
bash scripts/start.sh
```

The management installer installs a root-owned system service used only through a private Unix socket. Open the dashboard to create an administrator password of at least 12 characters. The dashboard does not receive Docker, D-Bus, or NetworkManager access. Enter the **antenna's actual latitude, longitude, and altitude above sea level in metres**. Feeder and Wi-Fi credentials are stored only on the Pi, never returned to the browser, excluded from Git, and protected by local file permissions. Keep a private backup. Choose only platforms you want to share with; provider account terms apply.

Open `http://<pi-ip>:8080` for AeroSignal. Find the IP with `hostname -I`. The dashboard proxies its integrated tar1090 interface under `/map/`, so users do not need to expose or connect to port 8081 separately. Receiver graphs are available under `/map/graphs1090/` when the upstream image provides them. Restart policies bring the services back after a reboot while Docker is enabled.

There are no fabricated aircraft in the app. Before a working receiver is connected, it shows an offline state. The overview radar is a station illustration; actual plotted positions and map controls are in tar1090. Aircraft without recent position reports may still appear in the traffic table.

## Feeder accounts

Configured integrations: Flightradar24, FlightAware, AirNav Radar, OpenSky Network, ADS-B.fi, ADSB.lol, Airplanes.live, Planespotters, The Air Traffic, ADS-B Exchange, AvDelphi, RadarPlane, and Fly Italy ADS-B. This is a defined set of integrations, not a guarantee of compatibility with every flight-data platform. Hosts and account requirements can change.

Community feeds can be selected directly in the wizard. The four account-based feeds need persistent identities:

- **Flightradar24:** create an account, then run `docker run -it --rm --entrypoint /usr/bin/fr24feed ghcr.io/sdr-enthusiasts/docker-flightradar24:latest --signup --configfile=/tmp/config.txt`. Follow the [container signup guide](https://github.com/sdr-enthusiasts/docker-flightradar24#obtaining-a-flightradar24-sharing-key-for-adsb). Choose a network Beast receiver, leave MLAT off, and save the issued sharing key in the wizard.
- **FlightAware:** obtain a persistent feeder ID following [PiAware's container guide](https://github.com/sdr-enthusiasts/docker-piaware#determining-your-feeder-id), enter it in the wizard, and [claim the receiver](https://flightaware.com/adsb/piaware/claim).
- **AirNav Radar:** generate a sharing key using the [AirNav container instructions](https://github.com/sdr-enthusiasts/docker-airnavradar#obtaining-a-airnav-radar-sharing-key), then enter it in the wizard. If enrolling against this stack, start local reception first and use `--network aerosignal_default` with `BEASTHOST=ultrafeeder` in the temporary registration container.
- **OpenSky:** register an account and obtain a serial using the [OpenSky container guide](https://github.com/sdr-enthusiasts/docker-opensky-network#obtaining-an-opensky-network-feeder-serial-number). Start local reception first; use `--network aerosignal_default` and `BEASTHOST=ultrafeeder` for registration. Save both username and serial in the wizard so the station identity survives restarts.

This release feeds ADS-B / Mode S at 1090 MHz. MLAT is disabled in the supplied account feeders and not configured for the community feeds. 978 MHz UAT needs a separate receiver and is not configured. Only Ultrafeeder owns the USB SDR; other containers consume its internal Beast stream. Beast ports are not published to the LAN.

Use **Feeder network** in the dashboard to enable platforms, save account keys, change the receiver location, and apply the services. Saved keys appear only as “saved securely”; they are never returned to the browser. If an apply fails, AeroSignal restores the previous `.env` and attempts to restore the previous services. Check `docker compose ps`, `docker compose logs --tail=100 ultrafeeder`, and each provider's station page. The dashboard intentionally labels selection as unverified; it does not invent successful delivery status.

## Wi-Fi and Ethernet

The **Network** page uses NetworkManager. When Ethernet is connected and has an IPv4 address, AeroSignal shows only the wired interface and hides Wi-Fi settings. Without Ethernet it can scan for Wi-Fi, join visible or hidden WPA2/WPA3 Personal networks, and configure DHCP or static IPv4. Enterprise Wi-Fi, bonding, VLANs, and static IPv6 are outside this release.

Before applying a change, AeroSignal asks you to review it. NetworkManager creates a system-level checkpoint with a two-minute timeout before any new profile is written or activated. Reconnect to AeroSignal at its new address and choose **Connection works · keep settings**. If you cannot reconnect, NetworkManager restores the previous state automatically. Keep a local console or known Ethernet connection available for the first network change. Existing profiles are left intact; AeroSignal creates a new profile with autoconnect disabled until you confirm it.

## GitHub and updates

The source includes `.github/workflows/check.yml`: GitHub runs Python tests, checks JavaScript and shell syntax, validates Compose, builds the dashboard container, and produces downloadable ZIP and tar.gz artifacts. It does not publish the local dashboard or use your feeder credentials.

The project repository is [TaxiwayBravo/AeroSignal](https://github.com/TaxiwayBravo/AeroSignal). Clone it on the Pi:

```bash
git clone https://github.com/TaxiwayBravo/AeroSignal.git aerosignal
cd aerosignal
python3 scripts/configure.py
sudo python3 scripts/install_manager.py
bash scripts/start.sh
```

For future updates:

```bash
bash scripts/update.sh
```

The updater refuses tracked local modifications, saves a private configuration backup and previous Git revision, uses `git pull --ff-only`, validates Compose, pulls container updates, and recreates services. Updates are explicit, not unattended. Upstream images use `latest`, so container updates are not reproducible; for controlled deployments replace image tags with tested digests and keep a known-good digest record. `backups/images-*.txt` records local image IDs, but is not an image backup and does not guarantee binary rollback.

To roll back application source, review `backups/revision-*`, check out that commit, and run the startup script. To roll back containers, restore known-good image digests separately. Preserve `.env` and named volumes. Do not use `docker compose down -v` unless you want to erase receiver history/graphs.

For ZIP installations, extract the new release into a new directory, copy the old private `.env` into it with mode 600, run `sudo python3 scripts/install_manager.py` from the new directory, then run its startup script. Compose's fixed project name keeps the existing receiver volumes. Do not run both versions simultaneously. Build archives yourself with `python3 scripts/package.py`.

## Original Pi / Zero dashboard-only mode

Install Python 3.9+ and extract the same package. Connect it to an existing readsb/tar1090 receiver reachable on your LAN. No Docker is required:

```bash
RECEIVER_URL=http://192.168.1.20:8081 \
MAP_URL=http://192.168.1.20:8081/ \
STATION_NAME='My receiver' \
python3 app/server.py
```

Replace the example address with your receiver. `RECEIVER_URL` must expose `/data/aircraft.json`. Open the old Pi's port 8080 from a modern browser. This mode displays another receiver; it does not install a local decoder or start feeders on ARMv6. A manual decoder compiled for an older Pi is outside this package. For persistence, adapt `docs/aerosignal-dashboard.service`, replacing paths, user, and receiver URLs, then install it under `/etc/systemd/system/` and enable it with systemctl.

## Operation and troubleshooting

- **No reception:** verify antenna, USB power, `lsusb`, correct device index/serial, and driver blacklist. Stop other dump1090/readsb services that already own the dongle. Check Ultrafeeder logs.
- **Offline dashboard but map works:** the upstream JSON must be at `/data/aircraft.json`; inspect the receiver clock and logs. Data older than 30 seconds is marked stale. Synchronise Pi time through the OS.
- **Map does not load:** open port 8081 directly. For custom ports or dashboard-only mode set `MAP_URL`. External tile servers may require internet. No offline tile bundle is included.
- **No platform data:** check keys, location, network access and container logs. A selected feed is not evidence that the remote platform accepted it.
- **Low memory:** reduce selected feeder containers and history usage; use dashboard-only mode on constrained boards.
- **Stop:** `docker compose --profile fr24 --profile flightaware --profile airnav --profile opensky down` preserves named volumes.
- **Management unavailable:** run `systemctl status aerosignal-manager` and `sudo journalctl -u aerosignal-manager`. Reinstall it from the current AeroSignal directory with `sudo python3 scripts/install_manager.py`.
- **Reset the station password:** run `sudo python3 scripts/install_manager.py --reset-password`, then immediately reload the dashboard and claim the station again.
- **Network change is pending:** reconnect to the old or new address and confirm it. If neither opens, wait two minutes for NetworkManager's checkpoint rollback, then reconnect to the previous address.
- **Security:** intended for a trusted LAN only. The settings UI is password protected, but HTTP does not encrypt traffic on your LAN. Do not expose ports 8080/8081 through a router; use a trusted VPN for remote access. `.env` is readable by root and Docker administrators. The browser-facing dashboard has no Docker socket, D-Bus mount, or direct NetworkManager access.

## Development and verification

```bash
python3 -m unittest discover -s tests -v
node --check app/static/app.js
bash -n scripts/start.sh scripts/update.sh scripts/prepare-usb.sh
python3 scripts/package.py
```

Local validation covers receiver freshness/error handling, password sessions and rate limiting, CSRF protection, credential masking, atomic configuration writes, feeder rollback, network input validation, checkpoint ordering and rollback, syntax, and dashboard navigation. Docker, NetworkManager, and an SDR were unavailable on the build machine, so Pi service installation, real network switching, container startup, tar1090 integration, and delivery to providers require a hardware acceptance test. The GitHub workflow validates the Compose build on each push; inspect the Actions result for the revision you install. See THIRD_PARTY.md for upstream components and docs/branding.md for the logo generation record.
