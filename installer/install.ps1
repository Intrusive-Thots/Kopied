# Kopied Installer Script
# Installs Kopied service and viewer to C:\Kopied

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "         Kopied Installer v1.0          " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Determine Repository Root
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Definition }
$repoRoot = Split-Path -Parent $scriptDir
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "bin"))) {
    # Fallback to standard workspace location if executed out of context
    $repoRoot = "C:\Projects\Loose_Workspaces\Kopied"
}

# 2. Create Directory Structure
Write-Host "Creating directory structure in C:\Kopied..." -ForegroundColor Cyan
$targetDirs = @(
    "C:\Kopied\bin",
    "C:\Kopied\gui",
    "C:\Kopied\index",
    "C:\Kopied\Clipboard\Text",
    "C:\Kopied\Clipboard\Images",
    "C:\Kopied\Screenshots"
)

try {
    foreach ($dir in $targetDirs) {
        if (-not (Test-Path -LiteralPath $dir)) {
            $null = New-Item -ItemType Directory -Path $dir -Force
            Write-Host "  Created: $dir" -ForegroundColor Green
        } else {
            Write-Host "  Exists: $dir" -ForegroundColor Green
        }
    }
} catch {
    Write-Host "Error creating directories: $_" -ForegroundColor Red
    exit 1
}

# 3. Copy Files from Repo Root to C:\Kopied
Write-Host "`nCopying files from repository..." -ForegroundColor Cyan
try {
    # Copy bin\*.py, bin\*.vbs, bin\*.bat -> C:\Kopied\bin\
    $binSource = Join-Path $repoRoot "bin"
    if (Test-Path -LiteralPath $binSource) {
        $binFiles = Get-ChildItem -LiteralPath $binSource -File | Where-Object { $_.Extension -in @(".py", ".vbs", ".bat") }
        foreach ($file in $binFiles) {
            Copy-Item -LiteralPath $file.FullName -Destination "C:\Kopied\bin\" -Force
            Write-Host "  Copied: bin\$($file.Name) -> C:\Kopied\bin\" -ForegroundColor Green
        }
    } else {
        throw "Source directory not found: $binSource"
    }

    # Copy gui\*.html -> C:\Kopied\gui\
    $guiSource = Join-Path $repoRoot "gui"
    if (Test-Path -LiteralPath $guiSource) {
        $guiFiles = Get-ChildItem -LiteralPath $guiSource -File -Filter "*.html"
        foreach ($file in $guiFiles) {
            Copy-Item -LiteralPath $file.FullName -Destination "C:\Kopied\gui\" -Force
            Write-Host "  Copied: gui\$($file.Name) -> C:\Kopied\gui\" -ForegroundColor Green
        }
    }

    # Copy README.md -> C:\Kopied\
    $readmeSource = Join-Path $repoRoot "README.md"
    if (Test-Path -LiteralPath $readmeSource) {
        Copy-Item -LiteralPath $readmeSource -Destination "C:\Kopied\" -Force
        Write-Host "  Copied: README.md -> C:\Kopied\" -ForegroundColor Green
    }
} catch {
    Write-Host "Error copying files: $_" -ForegroundColor Red
    exit 1
}

# 4. Check for Python 3 Availability
Write-Host "`nChecking for Python 3..." -ForegroundColor Cyan
$pythonFound = $false
try {
    $pyVersionOutput = & py -3 --version 2>&1
    if ($LASTEXITCODE -eq 0 -and $pyVersionOutput -match 'Python\s+3') {
        $pythonFound = $true
        Write-Host "  Python 3 detected: $pyVersionOutput" -ForegroundColor Green
    }
} catch {
    $pythonFound = $false
}

if (-not $pythonFound) {
    Write-Host "Error: Python 3 was not found via 'py -3 --version'." -ForegroundColor Red
    Write-Host "Please install Python 3.x from https://www.python.org and ensure Python launcher (py.exe) is included in installation." -ForegroundColor Red
    exit 1
}

# 5. Install Dependencies via pip (suppressing PATH warnings)
Write-Host "`nInstalling required Python packages (pywin32, Pillow)..." -ForegroundColor Cyan
try {
    & py -3 -m pip install --user --no-warn-script-location pywin32 Pillow
    if ($LASTEXITCODE -ne 0) {
        throw "pip installation failed with exit code $LASTEXITCODE"
    }
    Write-Host "  Packages installed successfully." -ForegroundColor Green
} catch {
    Write-Host "Error installing Python packages: $_" -ForegroundColor Red
    exit 1
}

# 6. Run install_startup.vbs for Startup shortcut
Write-Host "`nConfiguring Startup shortcuts..." -ForegroundColor Cyan
try {
    $startupVbs = "C:\Kopied\bin\install_startup.vbs"
    if (-not (Test-Path -LiteralPath $startupVbs)) {
        throw "Script not found at $startupVbs"
    }
    $vbsResult = & cscript //Nologo $startupVbs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "cscript execution failed with exit code ${LASTEXITCODE}: $vbsResult"
    }
    Write-Host "  Startup shortcut registered successfully." -ForegroundColor Green
} catch {
    Write-Host "Error running install_startup.vbs: $_" -ForegroundColor Red
    exit 1
}

# 7. Create Desktop Shortcut 'Kopied Viewer.lnk'
Write-Host "`nCreating Desktop shortcut..." -ForegroundColor Cyan
try {
    $wshShell = New-Object -ComObject WScript.Shell
    $desktopDir = $wshShell.SpecialFolders("Desktop")
    $shortcutPath = Join-Path $desktopDir "Kopied Viewer.lnk"
    $shortcut = $wshShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "wscript.exe"
    $shortcut.Arguments = "C:\Kopied\bin\launch_gui_silent.vbs"
    $shortcut.WorkingDirectory = "C:\Kopied"
    $shortcut.WindowStyle = 7
    $shortcut.Description = "Kopied Clipboard and Screenshot GUI Viewer"
    $shortcut.Save()
    Write-Host "  Desktop shortcut created: $shortcutPath" -ForegroundColor Green
} catch {
    Write-Host "Error creating desktop shortcut: $_" -ForegroundColor Red
    exit 1
}

# 8. Start Both Background Services
Write-Host "`nStarting Kopied services..." -ForegroundColor Cyan
try {
    Start-Process wscript -ArgumentList 'C:\Kopied\bin\launch_kopied.vbs'
    Start-Process wscript -ArgumentList 'C:\Kopied\bin\launch_gui_silent.vbs'
    Write-Host "  Services started (kopied daemon and GUI server)." -ForegroundColor Green
} catch {
    Write-Host "Error starting services: $_" -ForegroundColor Red
    exit 1
}

# 9. Wait 2 Seconds and Open Default Browser
Write-Host "`nWaiting 2 seconds for services to initialize..." -ForegroundColor Cyan
Start-Sleep -Seconds 2
try {
    Start-Process "http://127.0.0.1:8765"
} catch {
    Write-Host "Notice: Could not automatically open browser: $_" -ForegroundColor Cyan
}

# 10. Print Summary
Write-Host ""
Write-Host "=================================================================================" -ForegroundColor Green
Write-Host "Kopied installed successfully! Services are running. GUI at http://127.0.0.1:8765" -ForegroundColor Green
Write-Host "=================================================================================" -ForegroundColor Green
