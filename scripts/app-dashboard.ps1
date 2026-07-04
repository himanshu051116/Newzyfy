$ErrorActionPreference = "Stop"

$dashboardUrl = "http://127.0.0.1:8010/news-sources"
$healthUrl = "http://127.0.0.1:8010/api/v1/health/live"

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
        return
    }
}

try {
    $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
    if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        Start-Process -FilePath $dashboardUrl
        exit 0
    }
} catch {
    Show-LauncherMessage -Message "The app does not look like it is running yet. Use the Start shortcut first, then open the dashboard." -Seconds 10 -Icon 48
}

Start-Process -FilePath $dashboardUrl
