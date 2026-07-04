Option Explicit

Dim shell
Dim fso
Dim workspace
Dim scriptPath
Dim dashboardUrl
Dim command
Dim exitCode

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

workspace = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = workspace & "\scripts\run-platform.ps1"
dashboardUrl = "http://127.0.0.1:8010/news-sources"

If Not fso.FileExists(scriptPath) Then
    MsgBox _
        "Could not find:" & vbCrLf & scriptPath, _
        vbCritical, _
        "News Intelligence Platform"
    WScript.Quit 2
End If

command = _
    "powershell.exe -NoLogo -NoProfile " & _
    "-ExecutionPolicy Bypass " & _
    "-WindowStyle Hidden " & _
    "-File """ & scriptPath & """ start"

' 0 = hidden window
' True = wait until PowerShell finishes
exitCode = shell.Run(command, 0, True)

If exitCode = 0 Then
    shell.Run dashboardUrl, 1, False
Else
    MsgBox _
        "News Intelligence could not be started." & vbCrLf & vbCrLf & _
        "Check the logs in:" & vbCrLf & _
        workspace & "\.run\logs", _
        vbCritical, _
        "News Intelligence Platform"
End If

WScript.Quit exitCode