#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env || { echo 'Configure the station first.'; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo 'For ZIP installs, extract a new release and copy .env into it. See README.'; exit 1; }
test -z "$(git status --porcelain --untracked-files=no)" || { echo 'Commit or stash tracked local changes before updating.'; exit 1; }
mkdir -p backups
chmod 700 backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
cp .env "backups/env-$stamp"
chmod 600 "backups/env-$stamp"
git rev-parse HEAD > "backups/revision-$stamp"
docker compose images > "backups/images-$stamp.txt"
git pull --ff-only
docker compose config --quiet
docker compose pull
if systemctl is-active --quiet aerosignal-manager.service; then
  sudo python3 scripts/install_manager.py
fi
bash scripts/start.sh
echo "Update applied. Previous revision recorded in backups/revision-$stamp. Verify reception and provider delivery."
