# 14 — Management CLI (`isli`)

The `isli` CLI is a unified Python-based management tool designed to simplify the lifecycle of an ISLI AI deployment. It handles everything from initial configuration to production updates and data backups.

## Installation & Setup

### One-Tap Installation (Recommended)

The fastest way to install ISLI on a fresh VPS or local machine is using the bootstrap script:

```bash
# Download and run the bootstrap script
curl -sSL https://raw.githubusercontent.com/medelmouhajir/ISLI/main/scripts/install.sh -o install.sh

# Run the installer
bash install.sh
```

This script will:
1.  Check for dependencies (`python`).
2.  Set up an isolated virtual environment for management tools.
3.  Install `typer`, `rich`, `psutil`, and `python-dotenv`.
4.  Launch the interactive **Setup Wizard** (which begins with **Pre-flight Checks**).

## CLI Commands Reference

The CLI is located at `scripts/isli.py` and is typically run via the project's internal virtual environment.

### `isli preflight`
Runs system resource and network checks.
- **RAM Check:** Warns if < 8GB (required for local LLMs).
- **Disk Check:** Warns if < 20GB free space.
- **Port Check:** Verifies that ports 8000-8003, 5173, 80, 5432, and 6379 are available.

### `isli setup`
Launches the interactive wizard to configure your environment.
- **Pre-flight:** Runs `preflight` checks automatically.
- **Secret Generation:** Automatically creates secure `JWT_SECRET`, `PII_ENCRYPTION_KEY`, and `ADMIN_API_KEY`.
- **Ollama Detection:** Detects local/remote Ollama and pulls the required `qwen3:1.7b` model.
- **Domain Configuration:** Sets your `ISLI_DOMAIN` for reverse proxy routing.

### `isli up` / `isli down`
Wrappers for Docker Compose.
- `isli up`: Starts all 14 services in detached mode.
- `isli down -v`: Stops services and optionally nukes volumes.

### `isli status`
Provides a real-time health dashboard of all services.
- Checks Docker container states.
- Verifies health check status.
- **Exit Codes:** Returns `0` if all services are healthy, `1` if any are degraded (ideal for monitoring scripts).

### `isli update`
A hardened production update sequence with a mandatory safety net.
0.  **Auto-Backup:** Creates a pre-update snapshot of DB and workspace.
1.  **Stash:** Safely stashes local code modifications.
2.  **Pull:** Fetches latest code and Docker images.
3.  **Migrate:** Runs `alembic` database migrations.
4.  **Restart:** Recreates containers and verifies health.
- *Flags:* `--dry-run` to see what would change; `--skip-backup` to bypass safety.

### `isli backup` / `isli restore`
- `isli backup`: Dumps the PostgreSQL database and tars the `workspaces/` directory to `./backups/YYYYMMDD/`.
- `isli restore <path>`: Restores a specific backup snapshot.

### `isli reset --hard`
Nukes the environment for a clean start.
- Deletes all Docker volumes.
- Deletes the `.env` file.
- **Confirmation:** Requires typing `yes` explicitly to prevent accidental data loss.

### `isli skill` (Added 2026-06-12)
One-click skill lifecycle management from the terminal.

| Command | Purpose |
|---------|---------|
| `isli skill install <git-url>` | Install and auto-enable a skill from a public git repository |
| `isli skill install <git-url> --no-auto-enable` | Install only (status remains `pending`) |
| `isli skill enable <skill-id>` | Build and start a previously installed skill |
| `isli skill disable <skill-id>` | Stop a running skill container |
| `isli skill uninstall <skill-id>` | Remove a skill completely (image, source, DB row) |
| `isli skill list` | Table view of all installed skills with status, probe health, version, and category |

**Example:**
```bash
isli skill install https://github.com/isli-ai/skill-web-search
# → ✓ Skill 'skill-web-search' installed and enabled.
# → Build time: 12450ms
# → Health probe: OK

isli skill list
# → Table: ID | Name | Status | Probe | Version | Category
```

The CLI calls Core's admin endpoints directly using `urllib.request` and `X-Admin-Key` — no additional Python dependencies required.

## Operational Philosophy

The `isli` CLI is designed to be the "Human-in-the-Loop" interface for system operators. While the agents handle tasks and the Kanban board handles coordination, the CLI ensures the underlying infrastructure remains healthy, updated, and backed up.
