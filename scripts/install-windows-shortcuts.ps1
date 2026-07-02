param(
    [string] $ShortcutDirectory = [Environment]::GetFolderPath("Desktop")
)

$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$wscript = Join-Path $env:SystemRoot "System32\wscript.exe"
$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path $ShortcutDirectory)) {
    New-Item -ItemType Directory -Force -Path $ShortcutDirectory | Out-Null
}

$shell = New-Object -ComObject WScript.Shell

$shortcuts = @(
    @{
        Name = "News Intelligence - Start.lnk"
        TargetPath = $wscript
        Arguments = "`"$(Join-Path $workspace "Start-News-Intelligence.vbs")`""
        Description = "Start the News Intelligence Platform and open the dashboard."
        IconLocation = "$env:SystemRoot\System32\SHELL32.dll,137"
        WindowStyle = 7
    },
    @{
        Name = "News Intelligence - Stop.lnk"
        TargetPath = $wscript
        Arguments = "`"$(Join-Path $workspace "Stop-News-Intelligence.vbs")`""
        Description = "Stop the News Intelligence Platform local services."
        IconLocation = "$env:SystemRoot\System32\SHELL32.dll,109"
        WindowStyle = 7
    },
    @{
        Name = "News Intelligence - Dashboard.lnk"
        TargetPath = $wscript
        Arguments = "`"$(Join-Path $workspace "Open-News-Dashboard.vbs")`""
        Description = "Open the News Intelligence dashboard."
        IconLocation = "$env:SystemRoot\System32\SHELL32.dll,220"
        WindowStyle = 1
    },
    @{
        Name = "News Intelligence - Status.lnk"
        TargetPath = $powershell
        Arguments = "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$(Join-Path $workspace "scripts\run-platform.ps1")`" status"
        Description = "Show local service and Docker status."
        IconLocation = "$env:SystemRoot\System32\SHELL32.dll,23"
        WindowStyle = 1
    }
)

foreach ($item in $shortcuts) {
    $path = Join-Path $ShortcutDirectory $item.Name
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $item.TargetPath
    $shortcut.Arguments = $item.Arguments
    $shortcut.WorkingDirectory = $workspace
    $shortcut.Description = $item.Description
    $shortcut.IconLocation = $item.IconLocation
    $shortcut.WindowStyle = $item.WindowStyle
    $shortcut.Save()
    Write-Host "Created shortcut: $path"
}
