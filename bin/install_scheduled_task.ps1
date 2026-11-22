# Register a per-user Scheduled Task so the Kopied clipboard engine stays running.
# No admin required. Safe to re-run (replaces the Kopied task in the root folder).
# Also creates/refreshes the Desktop shortcut for the GUI.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File C:\Kopied\bin\install_scheduled_task.ps1

$ErrorActionPreference = 'Stop'

$KopiedRoot = 'C:\Kopied'
$Engine = Join-Path $KopiedRoot 'bin\kopied.py'
$Gui = Join-Path $KopiedRoot 'bin\kopied_gui.py'
$Icon = Join-Path $KopiedRoot 'assets\kopied.ico'
$TaskName = 'Kopied'
$Pythonw = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\pythonw.exe'

if (-not (Test-Path -LiteralPath $Pythonw)) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) { $Pythonw = $cmd.Source }
}
if (-not (Test-Path -LiteralPath $Pythonw)) {
    throw "pythonw.exe not found. Install Python 3 and retry."
}
if (-not (Test-Path -LiteralPath $Engine)) {
    throw "Kopied engine not found at $Engine"
}

$action = New-ScheduledTaskAction -Execute $Pythonw -Argument ('"{0}"' -f $Engine) -WorkingDirectory $KopiedRoot

$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# 15s delay so the user profile and clipboard service are up
$logon.Delay = 'PT15S'

# Second trigger: every 10 minutes, starts the engine only if the task is not already
# running (MultipleInstances = IgnoreNew). Combined with kopied.lock / mutex, this
# never double-starts. Covers a clean (exit 0) crash that RestartOnFailure would miss.
# ~10 years of 10-minute checks (indefinite Duration is rejected by some hosts)
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -DontStopOnIdleEnd

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

$desc = 'Kopied clipboard and screenshot archive engine (pythonw, background, restart on failure).'

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($logon, $repeat) -Settings $settings -Principal $principal -Description $desc -Force | Out-Null

# Confirm / repair execution time limit (0 sometimes means "default 72h")
$task = Get-ScheduledTask -TaskName $TaskName
if ($task.Settings.ExecutionTimeLimit -ne 'PT0S' -and $task.Settings.ExecutionTimeLimit -ne 'P0S' -and [string]$task.Settings.ExecutionTimeLimit -ne '00:00:00') {
    $task.Settings.ExecutionTimeLimit = 'PT0S'
    Set-ScheduledTask -InputObject $task | Out-Null
}

Write-Output ("Registered task '{0}' -> {1} {2}" -f $TaskName, $Pythonw, $Engine)

# Desktop shortcut for the GUI (no console), with the Kopied icon when present.
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'Kopied.lnk'
$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($lnkPath)
$sc.TargetPath = $Pythonw
$sc.Arguments = ('"{0}"' -f $Gui)
$sc.WorkingDirectory = $KopiedRoot
$sc.WindowStyle = 7
$sc.Description = 'Kopied clipboard and screenshot archive'
if (Test-Path -LiteralPath $Icon) {
    $sc.IconLocation = "$Icon,0"
}
$sc.Save()
Write-Output ("Shortcut: {0}" -f $lnkPath)
Write-Output ("  Target={0} {1}" -f $sc.TargetPath, $sc.Arguments)
Write-Output ("  Icon={0}" -f $sc.IconLocation)
