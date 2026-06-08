# ISLI Native Windows Installer (PowerShell)
# Checks Python/Node/Ollama, creates venvs, installs deps, creates Windows services.

param(
    [string]$InstallDir = "C:\ISLI"
)

$ErrorActionPreference = "Stop"

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Host "[install-native] ISLI native Windows installer" -ForegroundColor Cyan

# --- Checks ---
if (-not (Test-Command python)) {
    Write-Error "Python is not installed. Please install Python 3.12 from https://python.org"
    exit 1
}
if (-not (Test-Command node)) {
    Write-Error "Node.js is not installed. Please install Node.js 22 from https://nodejs.org"
    exit 1
}
if (-not (Test-Command psql)) {
    Write-Warning "PostgreSQL 'psql' not found. Please install PostgreSQL and add it to your PATH."
}
if (-not (Test-Command redis-server)) {
    Write-Warning "Redis 'redis-server' not found. Please install Redis for Windows (e.g., via Memurai or MSOpenTech)."
}

# --- Ollama Setup ---
if (-not (Test-Command ollama)) {
    Write-Host "[install-native] Ollama not found. Downloading installer..." -ForegroundColor Cyan
    $ollamaUrl = "https://ollama.com/download/OllamaSetup.exe"
    $installerPath = Join-Path $env:TEMP "OllamaSetup.exe"
    Invoke-WebRequest -Uri $ollamaUrl -OutFile $installerPath
    Write-Host "[install-native] Launching Ollama installer. Please complete the setup manually." -ForegroundColor Yellow
    Start-Process -FilePath $installerPath -Wait
}

Write-Host "[install-native] Pulling Keeper model (qwen3:1.7b)..." -ForegroundColor Cyan
& ollama pull qwen3:1.7b

# --- NSSM Setup ---
$nssmPath = Join-Path $InstallDir "nssm.exe"
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
}
if (-not (Test-Path $nssmPath)) {
    Write-Host "[install-native] Downloading NSSM..." -ForegroundColor Cyan
    $nssmZip = Join-Path $env:TEMP "nssm.zip"
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $nssmZip
    if (Test-Path (Join-Path $env:TEMP "nssm_temp")) { Remove-Item (Join-Path $env:TEMP "nssm_temp") -Recurse -Force }
    Expand-Archive -Path $nssmZip -DestinationPath (Join-Path $env:TEMP "nssm_temp") -Force
    Copy-Item -Path (Join-Path $env:TEMP "nssm_temp\nssm-2.24\win64\nssm.exe") -Destination $nssmPath
    Remove-Item (Join-Path $env:TEMP "nssm_temp") -Recurse -Force
}

# --- Create install dir ---
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Write-Host "[install-native] Copying project to $InstallDir"
Copy-Item -Path "$ProjectRoot\*" -Destination $InstallDir -Recurse -Force

# --- .env ---
$EnvFile = Join-Path $InstallDir ".env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item -Path (Join-Path $InstallDir ".env.production") -Destination $EnvFile -Force
    Write-Host "[install-native] Created .env from template." -ForegroundColor Yellow
}

# --- Python services ---
$services = @("isli-core", "isli-keeper", "isli-channels", "isli-skills")
foreach ($svc in $services) {
    Write-Host "[install-native] Setting up $svc..."
    $svcDir = Join-Path $InstallDir $svc
    $venvDir = Join-Path $svcDir ".venv"
    python -m venv $venvDir
    & "$venvDir\Scripts\pip.exe" install --upgrade pip
    & "$venvDir\Scripts\pip.exe" install -e "$svcDir[dev]"
}

# --- Board ---
Write-Host "[install-native] Setting up isli-board..."
$boardDir = Join-Path $InstallDir "isli-board"
Set-Location $boardDir
& npm ci
& npm run build
Set-Location $PSScriptRoot

# --- Windows Services via NSSM ---
Write-Host "[install-native] Creating Windows services with NSSM..." -ForegroundColor Cyan
foreach ($svc in $services) {
    $svcName = $svc
    $display = "ISLI $svc"
    $exe = Join-Path $InstallDir "$svc\.venv\Scripts\python.exe"
    $port = switch($svc){'isli-core'{8000}'isli-keeper'{8001}'isli-channels'{8002}'isli-skills'{8003}}
    $args = "-m uvicorn $($svc -replace '-','_').main:app --host 0.0.0.0 --port $port"
    
    # Remove if exists
    & $nssmPath remove $svcName confirm 2>$null
    
    & $nssmPath install $svcName $exe $args
    & $nssmPath set $svcName DisplayName $display
    & $nssmPath set $svcName AppDirectory (Join-Path $InstallDir $svc)
    & $nssmPath start $svcName
}

# Special case for board (using serve)
$boardSvc = "isli-board"
& $nssmPath remove $boardSvc confirm 2>$null
& $nssmPath install $boardSvc "node" "serve dist"
& $nssmPath set $boardSvc DisplayName "ISLI Board"
& $nssmPath set $boardSvc AppDirectory $boardDir
& $nssmPath start $boardSvc

Write-Host "[install-native] Done. Services are managed via Windows Service Manager (services.msc)" -ForegroundColor Green
Write-Host "[install-native] IMPORTANT: Edit $EnvFile if you changed database/redis settings." -ForegroundColor Yellow
