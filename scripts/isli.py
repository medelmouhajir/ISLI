import json
import os
import secrets
import shutil
import socket
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil
import typer
from dotenv import load_dotenv, set_key
from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.table import Table

app = typer.Typer(help="ISLI AI Management CLI")
console = Console()

# --- Configuration ---
PROJECT_ROOT = Path(__file__).parent.parent.parent # ISLI_AI root
ISLI_DIR = PROJECT_ROOT / "ISLI"
ENV_FILE = ISLI_DIR / ".env"
ENV_EXAMPLE = ISLI_DIR / ".env.example"
BACKUP_DIR = PROJECT_ROOT / "backups"

# --- Helpers ---
def run_command(cmd: str, check: bool = True, capture_output: bool = False):
    # Ensure we run from the directory containing docker-compose.yml
    return subprocess.run(cmd, shell=True, check=check, capture_output=capture_output, text=True, cwd=str(ISLI_DIR))

def get_env(key: str, default: str = "") -> str:
    load_dotenv(ENV_FILE)
    return os.getenv(key, default)

def generate_secret(length: int = 32) -> str:
    return secrets.token_hex(length // 2)

def check_docker():
    try:
        run_command("docker --version", capture_output=True)
        run_command("docker compose version", capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _core_api_url() -> str:
    domain = get_env("ISLI_DOMAIN", "localhost")
    if domain == "localhost":
        return "http://localhost:8000"
    return f"https://{domain}"


def _admin_api_key() -> str:
    return get_env("ADMIN_API_KEY", "")


def _api_request(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{_core_api_url()}{path}"
    headers = {
        "Content-Type": "application/json",
        "X-Admin-Key": _admin_api_key(),
    }
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status == 204:
            return {}
        return json.loads(resp.read().decode("utf-8"))


# --- Skill Sub-Commands ---
skill_app = typer.Typer(help="Manage ISLI skills")
app.add_typer(skill_app, name="skill")


@skill_app.command()
def install(url: str, skill_id: str = typer.Option(None, help="Override skill ID (defaults to repo name)"), auto_enable: bool = True):
    """Install a skill from a git URL."""
    if not skill_id:
        # Derive skill_id from last path segment of git URL, stripping .git
        skill_id = Path(url).name.replace(".git", "")

    endpoint = "/v1/skills/install-and-enable" if auto_enable else "/v1/skills/install"
    try:
        result = _api_request("POST", endpoint, {"skill_id": skill_id, "git_url": url})
        console.print(f"[green]✓ Skill '{skill_id}' installed{(' and enabled' if auto_enable else '')}.[/green]")
        if "build_time_ms" in result:
            console.print(f"[dim]Build time: {result['build_time_ms']}ms[/dim]")
        if "probe_ok" in result:
            console.print(f"[green]Health probe: {'OK' if result['probe_ok'] else 'FAILED'}[/green]")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        console.print(f"[red]✗ Installation failed: {e.code} {err_body}[/red]")
        raise typer.Exit(1)


@skill_app.command()
def enable(skill_id: str):
    """Enable a previously installed skill."""
    try:
        _api_request("POST", f"/v1/skills/{skill_id}/enable")
        console.print(f"[green]✓ Skill '{skill_id}' enabled.[/green]")
    except urllib.error.HTTPError as e:
        console.print(f"[red]✗ Enable failed: {e.code} {e.reason}[/red]")
        raise typer.Exit(1)


@skill_app.command()
def disable(skill_id: str):
    """Disable a running skill."""
    try:
        _api_request("POST", f"/v1/skills/{skill_id}/disable")
        console.print(f"[yellow]✓ Skill '{skill_id}' disabled.[/yellow]")
    except urllib.error.HTTPError as e:
        console.print(f"[red]✗ Disable failed: {e.code} {e.reason}[/red]")
        raise typer.Exit(1)


@skill_app.command()
def uninstall(skill_id: str):
    """Uninstall a skill completely."""
    if not typer.confirm(f"Are you sure you want to uninstall '{skill_id}'?"):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)
    try:
        _api_request("DELETE", f"/v1/skills/{skill_id}")
        console.print(f"[green]✓ Skill '{skill_id}' uninstalled.[/green]")
    except urllib.error.HTTPError as e:
        console.print(f"[red]✗ Uninstall failed: {e.code} {e.reason}[/red]")
        raise typer.Exit(1)


@skill_app.command("list")
def list_skills():
    """List all installed (non-builtin) skills."""
    try:
        skills = _api_request("GET", "/v1/skills")
        installed = [s for s in skills if s.get("status") != "builtin"]
        if not installed:
            console.print("[dim]No installed skills found.[/dim]")
            return

        table = Table(title="Installed Skills")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Status", style="bold")
        table.add_column("Probe", style="bold")
        table.add_column("Version", style="dim")
        table.add_column("Category", style="dim")

        for s in installed:
            status = s.get("status", "unknown")
            probe = s.get("last_probe_status", "n/a")
            style = "green" if status == "active" and probe == "healthy" else "red" if status == "error" else "yellow"
            table.add_row(
                s["name"],
                s.get("author", "") or "—",
                f"[{style}]{status}[/{style}]",
                probe,
                s.get("version", "") or "—",
                s.get("category", "custom"),
            )
        console.print(table)
    except urllib.error.HTTPError as e:
        console.print(f"[red]✗ List failed: {e.code} {e.reason}[/red]")
        raise typer.Exit(1)

def check_ollama():
    try:
        run_command("ollama --version", capture_output=True)
        return "local"
    except subprocess.CalledProcessError:
        # Check if remote URL is set in .env
        remote_url = get_env("KEEPER_OLLAMA_BASE_URL")
        if remote_url:
            return "remote"
        return None

def check_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) != 0

@app.command()
def preflight():
    """Run pre-flight system resource and network checks."""
    console.print(Panel.fit("ISLI AI Pre-flight Checks", style="bold cyan"))
    
    passed = True
    
    # 1. RAM Check
    ram = psutil.virtual_memory()
    total_ram_gb = ram.total / (1024**3)
    if total_ram_gb < 7.5: # Allow some margin for 8GB systems
        console.print(f"[yellow]⚠ Low RAM: {total_ram_gb:.1f}GB detected. 8GB+ is recommended for local LLMs.[/yellow]")
    else:
        console.print(f"[green]✓ RAM: {total_ram_gb:.1f}GB detected.[/green]")
        
    # 2. Disk Space Check
    disk = psutil.disk_usage(str(PROJECT_ROOT))
    free_gb = disk.free / (1024**3)
    if free_gb < 20:
        console.print(f"[yellow]⚠ Low Disk Space: {free_gb:.1f}GB free. 20GB+ is recommended.[/yellow]")
    else:
        console.print(f"[green]✓ Disk Space: {free_gb:.1f}GB free.[/green]")
        
    # 3. Port Conflicts
    required_ports = {
        8000: "isli-core",
        8001: "isli-keeper",
        8002: "isli-channels",
        8003: "isli-skills",
        5173: "isli-board (dev)",
        80: "isli-board (prod/proxy)",
        5432: "postgresql",
        6379: "redis"
    }
    
    console.print("\n[bold]Checking port availability...[/bold]")
    for port, svc in required_ports.items():
        if not check_port(port):
            console.print(f"[red]✗ Port {port} ({svc}) is already in use.[/red]")
            passed = False
        else:
            console.print(f"[green]✓ Port {port} available.[/green]")
            
    if not passed:
        console.print("\n[bold red]Pre-flight checks failed. Please resolve conflicts before continuing.[/bold red]")
        raise typer.Exit(1)
    
    console.print("\n[bold green]Pre-flight checks passed![/bold green]")

# --- Commands ---
@app.command()
def setup():
    """Interactive setup wizard for ISLI AI."""
    preflight()
    console.print(Panel.fit("Welcome to the ISLI AI Setup Wizard", style="bold cyan"))

    if not check_docker():
        console.print("[bold red]Error: Docker or Docker Compose not found.[/bold red]")
        console.print("Please install Docker and Docker Compose before continuing.")
        raise typer.Exit(1)

    if not ENV_FILE.exists():
        console.print(f"[yellow]Creating .env from {ENV_EXAMPLE.name}...[/yellow]")
        shutil.copy(ENV_EXAMPLE, ENV_FILE)

    # 1. Secret Generation
    with Status("Generating secure secrets...", console=console):
        for key in ["JWT_SECRET", "PII_ENCRYPTION_KEY", "ADMIN_API_KEY"]:
            if not get_env(key):
                secret = generate_secret()
                set_key(str(ENV_FILE), key, secret)
        
        # WhatsApp secrets if enabled
        if get_env("WHATSAPP_ENABLED") == "true":
            for key in ["SIDECAR_WEBHOOK_SECRET", "SIDECAR_API_TOKEN"]:
                if not get_env(key):
                    set_key(str(ENV_FILE), key, generate_secret())

    # 2. Ollama Detection
    ollama_status = check_ollama()
    if ollama_status == "local":
        console.print("[green]✓ Local Ollama detected.[/green]")
        if typer.confirm("Do you want to pull the Keeper model (qwen3:1.7b) now?", default=True):
            run_command("ollama pull qwen3:1.7b")
    elif ollama_status == "remote":
        console.print(f"[green]✓ Remote Ollama configured: {get_env('KEEPER_OLLAMA_BASE_URL')}[/green]")
    else:
        console.print("[yellow]! No Ollama detected.[/yellow]")
        console.print("ISLI requires Ollama for background intelligence. You can:")
        console.print(" 1. Install it at https://ollama.ai")
        console.print(" 2. Configure a remote endpoint in .env later.")
        console.print("[italic]ISLI will use cloud models (if configured) until Ollama is available.[/italic]")

    # 3. Domain / IP
    domain = typer.prompt("Enter your domain or IP (e.g., isli.example.com or 1.2.3.4)", default=get_env("ISLI_DOMAIN", "localhost"))
    set_key(str(ENV_FILE), "ISLI_DOMAIN", domain)

    console.print(Panel.fit("[bold green]Setup Complete![/bold green]\nRun [bold]isli up[/bold] to start the system.", style="green"))

@app.command()
def up(detach: bool = typer.Option(True, "--no-detach", help="Run in foreground")):
    """Start the ISLI AI stack."""
    cmd = "docker compose up"
    if detach:
        cmd += " -d"
    run_command(cmd)
    console.print("[green]ISLI is starting up...[/green]")

@app.command()
def down(volumes: bool = typer.Option(False, "--volumes", "-v", help="Remove volumes")):
    """Stop the ISLI AI stack."""
    cmd = "docker compose down"
    if volumes:
        cmd += " -v"
    run_command(cmd)
    console.print("[yellow]ISLI has been stopped.[/yellow]")

@app.command()
def status():
    """Check the health of all ISLI services."""
    try:
        result = run_command("docker compose ps --format json", capture_output=True)
        import json
        
        # docker compose ps --format json can return multiple JSON objects (one per line)
        lines = result.stdout.strip().split("\n")
        services = []
        for line in lines:
            if line.strip():
                try:
                    services.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        
        table = Table(title="ISLI Service Status")
        table.add_column("Service", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Health", style="bold")

        all_healthy = True
        for svc in services:
            status_text = svc.get("Status", "unknown")
            state = svc.get("State", "unknown")
            health = svc.get("Health", "n/a")
            
            style = "green" if state == "running" else "red"
            table.add_row(svc["Service"], f"[{style}]{status_text}[/{style}]", health)
            
            if state != "running":
                all_healthy = False

        console.print(table)
        
        if not all_healthy:
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]Error checking status: {e}[/red]")
        raise typer.Exit(1)

@app.command()
def backup(label: str = typer.Option("manual", help="Label for the backup")):
    """Back up the database and workspace."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"{label}_{timestamp}"
    backup_path.mkdir(parents=True, exist_ok=True)

    console.print(f"[cyan]Creating backup at {backup_path}...[/cyan]")
    
    # 1. DB Dump
    try:
        run_command(f"docker compose exec -t db pg_dump -U isli isli > {backup_path}/db_dump.sql")
    except Exception as e:
        console.print(f"[yellow]Warning: DB dump failed (is the DB running?): {e}[/yellow]")

    # 2. Workspace tar
    try:
        run_command(f"tar -czf {backup_path}/workspace.tar.gz -C {PROJECT_ROOT} ISLI/workspaces")
    except Exception as e:
        console.print(f"[yellow]Warning: Workspace backup failed: {e}[/yellow]")

    console.print(f"[bold green]Backup completed: {backup_path.name}[/bold green]")
    return backup_path

@app.command()
def update(dry_run: bool = typer.Option(False, "--dry-run", help="Show changes without executing"),
           skip_backup: bool = typer.Option(False, "--skip-backup", help="Skip automatic backup")):
    """Hardened update sequence for ISLI AI."""
    if dry_run:
        console.print("[cyan]Dry run mode: Showing planned actions...[/cyan]")
        console.print("1. isli backup --auto")
        console.print("2. git stash")
        console.print("3. git pull")
        console.print("4. docker compose pull")
        console.print("5. alembic upgrade head")
        console.print("6. docker compose up -d")
        return

    # 0. Backup
    if not skip_backup:
        backup(label="pre-update")

    # 1. Stash
    console.print("[cyan]Stashing local changes...[/cyan]")
    run_command("git stash")

    # 2. Pull
    console.print("[cyan]Pulling latest code...[/cyan]")
    run_command("git pull")

    # 3. Docker Pull
    console.print("[cyan]Pulling latest images...[/cyan]")
    run_command("docker compose pull")

    # 4. Migrations
    console.print("[cyan]Running database migrations...[/cyan]")
    run_command("docker compose run --rm core alembic upgrade head")

    # 5. Up
    console.print("[cyan]Restarting containers...[/cyan]")
    run_command("docker compose up -d")

    # 6. Status
    status()

@app.command()
def reset(hard: bool = typer.Option(False, "--hard", help="Nuke volumes and .env")):
    """Reset the ISLI environment."""
    if hard:
        console.print("[bold red]⚠️  CRITICAL WARNING: This will delete ALL volumes and your .env file![/bold red]")
        confirm = typer.prompt("Type 'yes' to confirm destruction")
        if confirm.lower() == 'yes':
            run_command("docker compose down -v")
            if ENV_FILE.exists():
                ENV_FILE.unlink()
            console.print("[bold green]Environment nuked successfully.[/bold green]")
        else:
            console.print("[yellow]Reset aborted.[/yellow]")
    else:
        console.print("Standard reset (restart containers)...")
        run_command("docker compose restart")

if __name__ == "__main__":
    app()
