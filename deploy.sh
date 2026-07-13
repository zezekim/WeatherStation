#!/usr/bin/env bash
#
# deploy.sh — decommission the old weather station and install the current
# version from GitHub, on the Raspberry Pi.
#
# What it does, idempotently:
#   1. Stops and disables the existing systemd services.
#   2. Updates /home/rs/weather to the latest main from GitHub, PRESERVING the
#      database, .env, and virtualenv (all gitignored — never touched by git).
#   3. Ensures the virtualenv exists and dependencies are installed.
#   4. Installs the systemd unit files from systemd/ and reloads systemd.
#   5. Enables and starts the services (only if .env is configured).
#
# Run it AS THE 'rs' USER (not root), so git keeps correct ownership; it calls
# sudo itself for the systemd steps. First-time bootstrap:
#
#   curl -fsSL https://raw.githubusercontent.com/zezekim/WeatherStation/main/deploy.sh -o /tmp/deploy.sh
#   bash /tmp/deploy.sh
#
# After the first run it lives at /home/rs/weather/deploy.sh.

set -euo pipefail

# --- Configuration -----------------------------------------------------------
REPO_URL="https://github.com/zezekim/WeatherStation.git"
APP_DIR="/home/rs/weather"
BRANCH="main"
RUN_USER="rs"
# systemd unit basenames, in start order (hubs/logger before the web app).
SERVICES=(modbus_hub pm25_hub mqtt_logger weather)

# --- Helpers -----------------------------------------------------------------
say()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!! \033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mxx \033[0m %s\n' "$*" >&2; exit 1; }

# --- Preconditions -----------------------------------------------------------
[ "$(id -u)" -ne 0 ] || die "Run as the '$RUN_USER' user, not root (sudo is used internally)."
command -v git  >/dev/null || die "git is not installed (sudo apt install git)."
command -v sudo >/dev/null || die "sudo is not available."
sudo -v || die "sudo authentication failed."

# --- 1. Stop & disable old services -----------------------------------------
say "Stopping and disabling existing services"
for svc in "${SERVICES[@]}"; do
    if systemctl list-unit-files "${svc}.service" >/dev/null 2>&1 \
       && systemctl cat "${svc}.service" >/dev/null 2>&1; then
        sudo systemctl stop "${svc}.service"    2>/dev/null || true
        sudo systemctl disable "${svc}.service" 2>/dev/null || true
        echo "   stopped ${svc}.service"
    fi
done
warn "If your old services used different names, stop them manually:"
warn "  systemctl list-units --type=service | grep -iE 'weather|hub|mqtt|modbus|pm25'"

# --- 2. Update code from GitHub (preserving data/.env/venv) ------------------
say "Updating code in $APP_DIR from $REPO_URL ($BRANCH)"
mkdir -p "$APP_DIR"
cd "$APP_DIR"
if [ ! -d .git ]; then
    # First deploy: adopt the existing directory as a git checkout in place.
    # Gitignored files (weather_data.db, .env, venv/, history.txt) are left
    # alone; tracked files are overwritten with the repo versions.
    git init -q -b "$BRANCH"
    git remote add origin "$REPO_URL"
fi
git remote set-url origin "$REPO_URL"
git fetch -q --depth 1 origin "$BRANCH"
git reset -q --hard FETCH_HEAD
echo "   now at $(git log -1 --format='%h %s')"

# --- 3. Virtualenv + dependencies -------------------------------------------
say "Ensuring virtualenv and dependencies"
if [ ! -x "$APP_DIR/venv/bin/python3" ]; then
    warn "No virtualenv found — creating one (this can take a while on a Pi)."
    python3 -m venv venv
fi
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -r requirements.txt
echo "   dependencies satisfied"

# Initialize the database only if it doesn't exist yet. init_db.py DROPS the
# table, so this guard makes sure we never wipe existing data.
if [ ! -f weather_data.db ]; then
    warn "No database found — creating a fresh one."
    ./venv/bin/python init_db.py
fi

# --- 4. .env check -----------------------------------------------------------
ENV_OK=1
if [ ! -f .env ]; then
    cp .env.example .env
    warn "Created .env from .env.example — you MUST edit it with real values."
    ENV_OK=0
elif grep -q "MQTT_PASS=changeme" .env || ! grep -q "^MQTT_PASS=..*" .env; then
    warn ".env is missing real MQTT credentials."
    ENV_OK=0
fi

# --- 5. Install systemd unit files ------------------------------------------
say "Installing systemd unit files"
for svc in "${SERVICES[@]}"; do
    sudo cp "systemd/${svc}.service" "/etc/systemd/system/${svc}.service"
    echo "   installed ${svc}.service"
done
sudo systemctl daemon-reload

# --- 6. Enable & start -------------------------------------------------------
say "Enabling services"
for svc in "${SERVICES[@]}"; do
    sudo systemctl enable "${svc}.service" >/dev/null 2>&1 || true
done

if [ "$ENV_OK" -eq 1 ]; then
    say "Starting services"
    for svc in "${SERVICES[@]}"; do
        sudo systemctl restart "${svc}.service"
        printf '   %-20s %s\n' "${svc}.service" "$(systemctl is-active "${svc}.service")"
    done
else
    warn "Services are enabled but NOT started — .env is not configured yet."
    warn "Edit $APP_DIR/.env, then run:  sudo systemctl start ${SERVICES[*]/%/.service}"
fi

# --- 7. Reminders ------------------------------------------------------------
say "Done."
echo "Dashboard:   http://$(hostname -I | awk '{print $1}'):5000"
echo "Logs:        journalctl -u weather.service -f"
echo
echo "Optional — nightly database compaction (keeps the DB small):"
echo "  crontab -e   # then add:"
echo "  15 3 * * *  cd $APP_DIR && venv/bin/python rollup.py --vacuum"
