$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$runDir = Join-Path $workspace ".run"
$logDir = Join-Path $runDir "logs"
$launcherLog = Join-Path $logDir "desktop-launcher.log"
$dashboardUrl = "http://127.0.0.1:8010/news-sources"
$healthUrl = "http://127.0.0.1:8010/api/v1/health/live"

function Ensure-LauncherDirs {
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

function Write-LauncherLog {
    param([string] $Message)

    $timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffK"
    Add-Content -Path $launcherLog -Value "[$timestamp] $Message"
}

function Show-LauncherMessage {
    param(
        [string] $Message,
        [string] $Title = "News Intelligence Platform",
        [int] $Seconds = 8,
        [int] $Icon = 64
    )

    try {
        $shell = New-Object -ComObject WScript.Shell
        $null = $shell.Popup($Message, $Seconds, $Title, $Icon)
    } catch {
        Write-LauncherLog "Popup failed: $($_.Exception.Message)"
    }
}

function Resolve-DockerCli {
    $standardDocker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path $standardDocker) {
        return $standardDocker
    }
    $dockerCommand = Get-Command docker -CommandType Application -ErrorAction SilentlyContinue
    if ($dockerCommand) {
        return $dockerCommand.Source
    }
    return $null
}

function Resolve-DockerDesktop {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe")
    )
    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"
    }
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return $null
}

function Test-DockerReady {
    param([string] $Docker)

    & $Docker info *> $null
    return $LASTEXITCODE -eq 0
}

function Start-DockerDesktopIfNeeded {
    $docker = Resolve-DockerCli
    if (-not $docker) {
        throw "Docker CLI was not found. Install Docker Desktop first."
    }
    if (Test-DockerReady -Docker $docker) {
        Write-LauncherLog "Docker is already ready."
        return
    }

    $dockerDesktop = Resolve-DockerDesktop
    if ($dockerDesktop) {
        Write-LauncherLog "Starting Docker Desktop: $dockerDesktop"
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
    } else {
        Write-LauncherLog "Docker Desktop executable was not found; waiting for Docker engine anyway."
    }

    for ($attempt = 1; $attempt -le 90; $attempt++) {
        Start-Sleep -Seconds 2
        if (Test-DockerReady -Docker $docker) {
            Write-LauncherLog "Docker became ready after attempt $attempt."
            return
        }
    }

    throw "Docker Desktop did not become ready within 3 minutes. Start Docker Desktop manually and try again."
}

function Invoke-LoggedScript {
    param(
        [string] $ScriptPath,
        [string[]] $Arguments
    )

    Write-LauncherLog "Running: $ScriptPath $($Arguments -join ' ')"
    & $ScriptPath @Arguments 2>&1 | ForEach-Object {
        Write-LauncherLog $_.ToString()
    }
}

function Wait-ForUrl {
    param(
        [string] $Url,
        [int] $Attempts = 60,
        [int] $DelaySeconds = 1
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
            Write-LauncherLog "Waiting for $Url failed on attempt ${attempt}: $($_.Exception.Message)"
        }
        Start-Sleep -Seconds $DelaySeconds
    }
    return $false
}

Ensure-LauncherDirs

try {
    Write-LauncherLog "Start requested."
    Start-DockerDesktopIfNeeded
    Invoke-LoggedScript -ScriptPath (Join-Path $workspace "scripts\run-platform.ps1") -Arguments @("start")

    if (Wait-ForUrl -Url $healthUrl) {
        Start-Process -FilePath $dashboardUrl
        Show-LauncherMessage -Message "News Intelligence is running. Dashboard opened in your browser."
    } else {
        Start-Process -FilePath $dashboardUrl
        Show-LauncherMessage -Message "Services were started, but the health check did not answer yet. If the dashboard is blank, wait a minute and refresh. Log: $launcherLog" -Seconds 12 -Icon 48
    }
} catch {
    Write-LauncherLog "Start failed: $($_.Exception.Message)"
    Show-LauncherMessage -Message "Could not start News Intelligence. Details are saved at: $launcherLog`n`n$($_.Exception.Message)" -Seconds 15 -Icon 16
    exit 1
}
