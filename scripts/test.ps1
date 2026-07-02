$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Run scripts/bootstrap.ps1 first."
}

function Invoke-CheckedPython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]] $Arguments)

    & $python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: python $($Arguments -join ' ')"
    }
}

Invoke-CheckedPython -m ruff check backend
Invoke-CheckedPython -m mypy backend\src
Invoke-CheckedPython -m pytest
