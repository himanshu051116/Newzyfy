param(
    [ValidateSet("init", "up", "down", "restart", "status", "logs", "migrate", "doctor")]
    [string] $Command = "status"
)

$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$docker = $null
$standardDocker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"

if (Test-Path $standardDocker) {
    $docker = $standardDocker
} else {
    $dockerCommand = Get-Command docker -CommandType Application -ErrorAction SilentlyContinue
    if ($dockerCommand) {
        $docker = $dockerCommand.Source
    }
}

if (-not $docker) {
    throw "Docker CLI was not found. Start Docker Desktop, then reopen PowerShell or install Docker Desktop."
}

$dockerDir = Split-Path -Parent $docker
if ($dockerDir -and ($env:Path -notlike "*$dockerDir*")) {
    $env:Path = "$dockerDir;$env:Path"
}

$python = Join-Path $workspace ".venv\Scripts\python.exe"
$alembic = Join-Path $workspace ".venv\Scripts\alembic.exe"

function Assert-LastCommandSucceeded {
    param([string] $Label)

    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Label"
    }
}

function Invoke-Compose {
    param([string[]] $ComposeArguments)
    & $docker compose @ComposeArguments
    Assert-LastCommandSucceeded "docker compose $($ComposeArguments -join ' ')"
}

function Invoke-Migrate {
    if (-not (Test-Path $alembic)) {
        throw "Alembic was not found. Run scripts/bootstrap.ps1 first."
    }
    & $alembic -c backend\alembic.ini upgrade head
    Assert-LastCommandSucceeded "alembic upgrade head"
}

function Invoke-Doctor {
    if (-not (Test-Path $python)) {
        throw "Python venv was not found. Run scripts/bootstrap.ps1 first."
    }
    & $python -m newsintel.doctor
    Assert-LastCommandSucceeded "python -m newsintel.doctor"
}

Push-Location $workspace
try {
    switch ($Command) {
        "init" {
            Invoke-Compose @("up", "--detach", "postgres", "redis", "qdrant", "minio")
            Invoke-Migrate
            Invoke-Doctor
            Invoke-Compose @("ps")
        }
        "up" {
            Invoke-Compose @("up", "--detach", "postgres", "redis", "qdrant", "minio")
        }
        "down" {
            Invoke-Compose @("down")
        }
        "restart" {
            Invoke-Compose @("restart", "postgres", "redis", "qdrant", "minio")
        }
        "status" {
            Invoke-Compose @("ps")
        }
        "logs" {
            Invoke-Compose @("logs", "--follow", "--tail", "100")
        }
        "migrate" {
            Invoke-Migrate
        }
        "doctor" {
            Invoke-Doctor
        }
    }
} finally {
    Pop-Location
}
