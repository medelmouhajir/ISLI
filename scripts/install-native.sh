#!/usr/bin/env bash
# Native install script for Linux (systemd).
# Installs Python 3.12, Node 22, creates venvs, systemd units, and starts services.
# Usage: ./scripts/install-native.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/isli}"

echo "[install-native] ISLI native Linux installer"

# --- Checks ---
if [[ $EUID -ne 0 ]]; then
   echo "[install-native] Please run as root (or with sudo)"
   exit 1
fi

# --- Dependencies ---
echo "[install-native] Installing dependencies..."
apt-get update -qq
apt-get install -y -qq python3.12 python3.12-venv python3-pip nodejs npm curl redis-server postgresql postgresql-contrib libpq-dev build-essential

# --- Create install dir ---
mkdir -p "${INSTALL_DIR}"
cp -r "${PROJECT_ROOT}"/* "${INSTALL_DIR}/"

# --- .env ---
if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
    cp "${INSTALL_DIR}/.env.production" "${INSTALL_DIR}/.env"
fi

# --- Python services ---
for svc in isli-core isli-keeper isli-channels isli-skills; do
    echo "[install-native] Setting up ${svc}..."
    svc_dir="${INSTALL_DIR}/${svc}"
    python3.12 -m venv "${svc_dir}/.venv"
    "${svc_dir}/.venv/bin/pip" install --upgrade pip
    "${svc_dir}/.venv/bin/pip" install -e "${svc_dir}[dev]"
done

# --- Board ---
echo "[install-native] Setting up isli-board..."
cd "${INSTALL_DIR}/isli-board"
npm ci
npm run build

# --- Database ---
echo "[install-native] Creating PostgreSQL database and user..."
su - postgres -c "psql -c \"CREATE USER isli WITH PASSWORD 'password';\"" 2>/dev/null || true
su - postgres -c "psql -c \"CREATE DATABASE isli OWNER isli;\"" 2>/dev/null || true
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE isli TO isli;\"" 2>/dev/null || true

# --- Redis ---
systemctl enable redis-server
systemctl start redis-server

# --- systemd units ---
echo "[install-native] Installing systemd services..."
cp "${INSTALL_DIR}/systemd/"*.service /etc/systemd/system/
systemctl daemon-reload

for svc in isli-core isli-keeper isli-channels isli-skills isli-board; do
    systemctl enable "${svc}"
    systemctl start "${svc}"
done

echo "[install-native] Done. Check status with: systemctl status isli-core"
