# Kopied Uninstaller Script
# Stops services, removes shortcuts, and cleans up Kopied installation

$ErrorActionPreference = "Continue"

# 1. Print Banner
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "           Kopied Uninstaller           " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 2. & 3. Kill running Kopied processes and wscript runners
Write-Host "Stopping running Kopied processes..." -ForegroundColor Cyan
try {
    $processesToStop = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $cmd = $_.CommandLine
        if ([string]::IsNullOrWhiteSpace($cmd)) {
            return $false
        }

        # 2. Kopied python processes (kopied.py, kopied_gui.py)
        $isPythonKopied = ($cmd -match 'kopied\.py' -or $cmd -match 'kopied_gui\.py')
        
        # 3. wscript.exe running launch_kopied.vbs or launch_gui_silent.vbs
        $isWscriptKopied = ($_.Name -match '^(wscript|cscript)\.exe$' -and ($cmd -match 'launch_kopied\.vbs' -or $cmd -match 'launch_gui_silent\.vbs'))

        return ($isPythonKopied -or $isWscriptKopied)
    }

    if ($processesToStop) {
        foreach ($proc in $processesToStop) {
            try {
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
                Write-Host "  Terminated process: $($proc.Name) (PID: $($proc.ProcessId))" -ForegroundColor Green
            } catch {
                Write-Host "  Could not terminate process $($proc.ProcessId): $_" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "  No running Kopied processes detected." -ForegroundColor Green
    }
} catch {
    Write-Host "Error querying processes: $_" -ForegroundColor Red
}

# 4. Remove Startup shortcuts: Kopied.lnk and Kopied GUI.lnk
Write-Host "`nRemoving Startup shortcuts..." -ForegroundColor Cyan
try {
    $startupPaths = @(
        [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Startup),
        [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::CommonStartup)
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique

    $startupShortcutNames = @("Kopied.lnk", "Kopied GUI.lnk")

    foreach ($sDir in $startupPaths) {
        foreach ($scName in $startupShortcutNames) {
            $shortcutFile = Join-Path $sDir $scName
            if (Test-Path -LiteralPath $shortcutFile) {
                try {
                    Remove-Item -LiteralPath $shortcutFile -Force
                    Write-Host "  Removed: $shortcutFile" -ForegroundColor Green
                } catch {
                    Write-Host "  Failed to remove ${shortcutFile}: $_" -ForegroundColor Red
                }
            }
        }
    }
} catch {
    Write-Host "Error processing Startup shortcuts: $_" -ForegroundColor Red
}

# 5. Remove Desktop shortcut: Kopied Viewer.lnk
Write-Host "`nRemoving Desktop shortcut..." -ForegroundColor Cyan
try {
    $desktopPaths = @(
        [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop),
        [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::CommonDesktop)
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique

    $desktopShortcutName = "Kopied Viewer.lnk"

    foreach ($dDir in $desktopPaths) {
        $desktopFile = Join-Path $dDir $desktopShortcutName
        if (Test-Path -LiteralPath $desktopFile) {
            try {
                Remove-Item -LiteralPath $desktopFile -Force
                Write-Host "  Removed: $desktopFile" -ForegroundColor Green
            } catch {
                Write-Host "  Failed to remove ${desktopFile}: $_" -ForegroundColor Red
            }
        }
    }
} catch {
    Write-Host "Error processing Desktop shortcut: $_" -ForegroundColor Red
}

# 6. Ask user about deleting clipboard data in C:\Kopied
Write-Host ""
$choice = Read-Host "Delete all clipboard data in C:\Kopied? (y/N)"
if ($choice -match '^[yY]') {
    try {
        if (Test-Path -LiteralPath "C:\Kopied") {
            Start-Sleep -Milliseconds 500
            Remove-Item -LiteralPath "C:\Kopied" -Recurse -Force
            Write-Host "C:\Kopied and all contained data removed." -ForegroundColor Green
        } else {
            Write-Host "Directory C:\Kopied does not exist." -ForegroundColor Cyan
        }
    } catch {
        Write-Host "Error removing C:\Kopied: $_" -ForegroundColor Red
    }
} else {
    Write-Host "Data preserved at C:\Kopied" -ForegroundColor Cyan
}

# 7. Print completion message
Write-Host ""
Write-Host "Kopied uninstalled." -ForegroundColor Green
