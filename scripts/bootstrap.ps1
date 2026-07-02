$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $workspace ".venv"

if (-not (Test-Path $venv)) {
    python -m venv $venv
}

$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -e "${workspace}[dev]"

Write-Host "Development environment ready."
