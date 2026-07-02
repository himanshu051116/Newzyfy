param(
    [ValidateSet("start", "stop", "status", "restart", "logs")]
    [string] $Command = "start"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

$workspace = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$python = Join-Path $workspace ".venv\Scripts\python.exe"
$runDir = Join-Path $workspace ".run"
$logDir = Join-Path $runDir "logs"
$servicesScript = Join-Path $workspace "scripts\services.ps1"

# Allow the API, poller and article worker to import the newsintel package.
$env:PYTHONPATH = Join-Path $workspace "backend\src"

# Write Python output to log files immediately instead of buffering it.
$env:PYTHONUNBUFFERED = "1"

if (-not (Test-Path $python)) {
    throw "Python virtual environment was not found at: $python`nRun scripts\bootstrap.ps1 first."
}

if (-not (Test-Path $servicesScript)) {
    throw "Service-management script was not found at: $servicesScript"
}

# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

function Ensure-RunDirs {
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

function Service-PidPath {
    param(
        [Parameter(Mandatory)]
        [string] $Name
    )

    return Join-Path $runDir "$Name.pid"
}

function Get-NewsServicePid {
    param(
        [Parameter(Mandatory)]
        [string] $Name
    )

    $pidPath = Service-PidPath -Name $Name

    if (-not (Test-Path $pidPath)) {
        return $null
    }

    $rawPid = (Get-Content -Path $pidPath -Raw).Trim()
    $pidValue = 0

    if (-not [int]::TryParse($rawPid, [ref] $pidValue)) {
        Write-Warning "${Name}: invalid PID file detected. Removing it."
        Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
        return $null
    }

    return $pidValue
}

# ---------------------------------------------------------------------------
# Start service
# ---------------------------------------------------------------------------

function Start-NewsService {
    param(
        [Parameter(Mandatory)]
        [string] $Name,

        [Parameter(Mandatory)]
        [string[]] $Arguments
    )

    Ensure-RunDirs

    $pidPath = Service-PidPath -Name $Name
    $existingPid = Get-NewsServicePid -Name $Name

    if ($null -ne $existingPid) {
        $existingProcess = Get-Process `
            -Id $existingPid `
            -ErrorAction SilentlyContinue

        if ($null -ne $existingProcess) {
            Write-Host "${Name}: already running with PID $existingPid"
            return
        }

        Write-Host "${Name}: removing stale PID file."
        Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
    }

    $stdout = Join-Path $logDir "$Name.out.log"
    $stderr = Join-Path $logDir "$Name.err.log"

    # Start with fresh logs for this run.
    Remove-Item -Path $stdout -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $stderr -Force -ErrorAction SilentlyContinue

    Write-Host "Starting ${Name}..."

    $process = Start-Process `
        -FilePath $python `
        -ArgumentList $Arguments `
        -WorkingDirectory $workspace `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru

    # Give Python a moment to fail immediately if imports or configuration
    # are invalid.
    Start-Sleep -Milliseconds 800

    $process.Refresh()

    if ($process.HasExited) {
        $errorOutput = ""

        if (Test-Path $stderr) {
            $errorOutput = (
                Get-Content -Path $stderr -Tail 40 -ErrorAction SilentlyContinue
            ) -join [Environment]::NewLine
        }

        throw @"
${Name} stopped immediately with exit code $($process.ExitCode).

Error log:
$errorOutput

Full log:
$stderr
"@
    }

    Set-Content `
        -Path $pidPath `
        -Value $process.Id `
        -Encoding ASCII

    Write-Host "${Name}: started with PID $($process.Id)"
    Write-Host "${Name}: standard output log: $stdout"
    Write-Host "${Name}: error log: $stderr"
}

# ---------------------------------------------------------------------------
# Stop service
# ---------------------------------------------------------------------------

function Stop-NewsService {
    param(
        [Parameter(Mandatory)]
        [string] $Name
    )

    $pidPath = Service-PidPath -Name $Name
    $pidValue = Get-NewsServicePid -Name $Name

    if ($null -eq $pidValue) {
        Write-Host "${Name}: stopped"
        return
    }

    $process = Get-Process `
        -Id $pidValue `
        -ErrorAction SilentlyContinue

    if ($null -ne $process) {
        Write-Host "Stopping ${Name} with PID $pidValue..."

        Stop-Process `
            -Id $pidValue `
            -Force `
            -ErrorAction SilentlyContinue

        try {
            Wait-Process `
                -Id $pidValue `
                -Timeout 10 `
                -ErrorAction SilentlyContinue
        }
        catch {
            Write-Warning "${Name}: process did not stop within the waiting period."
        }

        Write-Host "${Name}: stopped"
    }
    else {
        Write-Host "${Name}: stale PID $pidValue removed"
    }

    Remove-Item `
        -Path $pidPath `
        -Force `
        -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# Show service status
# ---------------------------------------------------------------------------

function Show-NewsService {
    param(
        [Parameter(Mandatory)]
        [string] $Name
    )

    $pidPath = Service-PidPath -Name $Name
    $pidValue = Get-NewsServicePid -Name $Name

    if ($null -eq $pidValue) {
        Write-Host "${Name}: stopped"
        return
    }

    $process = Get-Process `
        -Id $pidValue `
        -ErrorAction SilentlyContinue

    if ($null -ne $process) {
        Write-Host "${Name}: running PID $pidValue"
    }
    else {
        Write-Host "${Name}: stale PID $pidValue"

        Remove-Item `
            -Path $pidPath `
            -Force `
            -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------------
# Wait for FastAPI
# ---------------------------------------------------------------------------

function Wait-ForApi {
    param(
        [int] $TimeoutSeconds = 45
    )

    $healthUrl = "http://127.0.0.1:8000/api/v1/health/live"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    Write-Host "Waiting for the News Intelligence API..."

    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest `
                -Uri $healthUrl `
                -UseBasicParsing `
                -TimeoutSec 3 `
                -ErrorAction Stop

            if ($response.StatusCode -eq 200) {
                Write-Host "API: ready"
                return
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    throw "The API did not become ready within $TimeoutSeconds seconds. Check: $logDir\api.err.log"
}

function Show-ApiStatus {
    $statusUrl = "http://127.0.0.1:8000/api/v1/status"

    try {
        $response = Invoke-WebRequest `
            -Uri $statusUrl `
            -UseBasicParsing `
            -TimeoutSec 3 `
            -ErrorAction Stop

        $status = $response.Content | ConvertFrom-Json

        Write-Host ""
        Write-Host "Application status:"
        Write-Host "Database revision: $($status.database_revision)"
        Write-Host "Stored articles: $($status.article_count)"
        Write-Host "Last committed article: $($status.last_committed_article_at)"
        Write-Host "Queue depth: $($status.queue_depth)"
        Write-Host "Oldest pending candidate: $($status.oldest_pending_candidate_at)"
        Write-Host "Pending outbox events: $($status.pending_outbox_events)"
    }
    catch {
        Write-Host ""
        Write-Host "Application status: API not reachable yet."
    }
}

function Show-ServiceLogs {
    Ensure-RunDirs

    Write-Host "Tailing service logs from: $logDir"
    Write-Host "Press Ctrl+C to stop tailing."

    $paths = @(
        (Join-Path $logDir "api.out.log"),
        (Join-Path $logDir "api.err.log"),
        (Join-Path $logDir "poller.out.log"),
        (Join-Path $logDir "poller.err.log"),
        (Join-Path $logDir "articles.out.log"),
        (Join-Path $logDir "articles.err.log"),
        (Join-Path $logDir "outbox.out.log"),
        (Join-Path $logDir "outbox.err.log")
    ) | Where-Object { Test-Path $_ }

    if (-not $paths) {
        Write-Host "No service logs found yet. Start the platform first."
        return
    }

    Get-Content -Path $paths -Tail 80 -Wait
}

# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------

Push-Location $workspace

try {
    switch ($Command) {
        "start" {
            Ensure-RunDirs

            Write-Host "Starting database and supporting containers..."
            & $servicesScript init

            try {
                Start-NewsService `
                    -Name "api" `
                    -Arguments @(
                        "-m",
                        "uvicorn",
                        "newsintel.main:app",
                        "--app-dir",
                        "backend/src",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000"
                    )

                Start-NewsService `
                    -Name "poller" `
                    -Arguments @(
                        "-m",
                        "newsintel.workers.poller"
                    )

                Start-NewsService `
                    -Name "articles" `
                    -Arguments @(
                        "-m",
                        "newsintel.workers.articles"
                    )

                Start-NewsService `
                    -Name "outbox" `
                    -Arguments @(
                        "-m",
                        "newsintel.workers.outbox"
                    )

                Wait-ForApi -TimeoutSeconds 45

                Write-Host ""
                Write-Host "News Intelligence Platform started successfully."
                Write-Host "Dashboard: http://127.0.0.1:8000/news-sources"
                Write-Host "API documentation: http://127.0.0.1:8000/docs"
                Write-Host "Logs: $logDir"
            }
            catch {
                Write-Warning "Startup failed. Stopping partially started services."

                Stop-NewsService -Name "outbox"
                Stop-NewsService -Name "articles"
                Stop-NewsService -Name "poller"
                Stop-NewsService -Name "api"

                throw
            }
        }

        "stop" {
            Stop-NewsService -Name "outbox"
            Stop-NewsService -Name "articles"
            Stop-NewsService -Name "poller"
            Stop-NewsService -Name "api"

            Write-Host ""
            Write-Host "News Intelligence application services stopped."
            Write-Host "Stored publishers and articles were not deleted."
        }

        "restart" {
            & $PSCommandPath stop
            & $PSCommandPath start
        }

        "status" {
            Ensure-RunDirs

            Show-NewsService -Name "api"
            Show-NewsService -Name "poller"
            Show-NewsService -Name "articles"
            Show-NewsService -Name "outbox"
            Show-ApiStatus

            Write-Host ""
            Write-Host "Container status:"
            & $servicesScript status
        }

        "logs" {
            Show-ServiceLogs
        }
    }
}
finally {
    Pop-Location
}
