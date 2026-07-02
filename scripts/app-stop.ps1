$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$runDir = Join-Path $workspace ".run"
$logDir = Join-Path $runDir "logs"
$launcherLog = Join-Path $logDir "desktop-launcher.log"

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

Ensure-LauncherDirs

try {
    Write-LauncherLog "Stop requested."
    Invoke-LoggedScript -ScriptPath (Join-Path $workspace "scripts\run-platform.ps1") -Arguments @("stop")
    try {
        Invoke-LoggedScript -ScriptPath (Join-Path $workspace "scripts\services.ps1") -Arguments @("down")
    } catch {
        Write-LauncherLog "Docker infrastructure stop skipped or failed: $($_.Exception.Message)"
    }
    Show-LauncherMessage -Message "News Intelligence has been stopped."
} catch {
    Write-LauncherLog "Stop failed: $($_.Exception.Message)"
    Show-LauncherMessage -Message "Could not fully stop News Intelligence. Details are saved at: $launcherLog`n`n$($_.Exception.Message)" -Seconds 15 -Icon 16
    exit 1
}
