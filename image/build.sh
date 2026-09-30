#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="${1:-/tmp/aerosignal-pi-gen}"
branch="${2:-arm64}"
git clone --branch "$branch" --depth 1 https://github.com/RPi-Distro/pi-gen.git "$work"
cp -a "$root/image/stage-aerosignal" "$work/"
cp -a "$root" "$work/aerosignal-source"
rm -rf "$work/aerosignal-source/.git" "$work/aerosignal-source/.pi-gen"
chmod +x "$work/stage-aerosignal/prerun.sh" "$work/stage-aerosignal/00-install/"*.sh
cat > "$work/config" <<EOF
IMG_NAME=AeroSignal
RELEASE=trixie
DEPLOY_COMPRESSION=xz
ENABLE_SSH=0
LOCALE_DEFAULT=en_GB.UTF-8
KEYBOARD_KEYMAP=gb
KEYBOARD_LAYOUT="English (UK)"
TIMEZONE_DEFAULT=Europe/London
WPA_COUNTRY=GB
STAGE_LIST="stage0 stage1 stage2 stage-aerosignal"
EOF
cd "$work"
./build-docker.sh
echo "Image created under $work/deploy"
