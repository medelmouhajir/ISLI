# Runbook: Native Deployment (No Docker)

Deploy ISLI directly on the host OS. Suitable for:
- Windows PCs or laptops with sufficient resources
- Linux PCs or laptops
- Air-gapped environments where Docker is not available

## Prerequisites

### All Platforms

- Python 3.12
- Node.js 22 + npm
- PostgreSQL 16 (recommended for production) or SQLite (dev / single-PC)
- Redis 7

### Linux

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip nodejs npm redis-server postgresql postgresql-contrib libpq-dev build-essential
```

### Windows

1. Install Python 3.12 from https://python.org
2. Install Node.js 22 from https://nodejs.org
3. Install PostgreSQL 16 from https://postgresql.org/download/windows/
4. Install Redis for Windows (e.g., Memurai or native Redis 7 port)

## Install Steps

### Linux (systemd)

```bash
git clone https://github.com/medelmouhajir/ISLI.git
cd ISLI

# Run the automated installer (creates venvs, systemd units, DB)
sudo ./scripts/install-native.sh
```

After installation:
- Edit `/opt/isli/.env` with your secrets
- Start services: `sudo systemctl start isli-core`
- Check status: `sudo systemctl status isli-core`
- View logs: `sudo journalctl -u isli-core -f`

### Windows (PowerShell)

```powershell
git clone https://github.com/medelmouhajir/ISLI.git
cd ISLI

# Run the automated installer (creates venvs, start/stop scripts)
.\scripts\install-native.ps1 -InstallDir C:\ISLI
```

After installation:
- Edit `C:\ISLI\.env` with your secrets
- Start services: `& 'C:\ISLI\start-isli.ps1'`
- Stop services: `& 'C:\ISLI\stop-isli.ps1'`

## Manual Setup (Any OS)

If you prefer manual control:

### 1. Environment

```bash
cp .env.production .env
# Edit .env: set JWT_SECRET, PII_ENCRYPTION_KEY, POSTGRES_PASSWORD, etc.
```

### 2. Python Services

For each service (`isli-core`, `isli-keeper`, `isli-channels`, `isli-skills`):

```bash
cd isli-core
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m uvicorn isli_core.main:app --host 0.0.0.0 --port 8000
```

Repeat for each service on ports 8000–8003.

### 3. Board

```bash
cd isli-board
npm ci
npm run build
npx serve dist -l 80
```

### 4. Database

If using PostgreSQL:

```bash
sudo -u postgres psql -c "CREATE USER isli WITH PASSWORD 'password';"
sudo -u postgres psql -c "CREATE DATABASE isli OWNER isli;"
```

If using SQLite (dev / single PC only):

Set `DATABASE_URL=sqlite+aiosqlite:///./isli_prod.db` in `.env`.

## Notes

- SQLite is easier for a single PC but does not scale and lacks some PostgreSQL features (e.g., `ARRAY` columns). Use PostgreSQL for production.
- On Windows, you can optionally use NSSM to wrap Python processes as Windows services.
- Ensure ports 8000–8003 and 80 are free before starting.
