import os
import secrets
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

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

# --- Commands ---
@app.command()
def setup():
    """Interactive setup wizard for ISLI AI."""
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
