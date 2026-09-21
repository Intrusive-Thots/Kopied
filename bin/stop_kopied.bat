@echo off
echo Stopping Kopied service loop and process...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -match 'wscript.exe' -and $_.CommandLine -match 'launch_kopied\.vbs') -or (($_.Name -match 'python' -or $_.Name -match 'py') -and $_.CommandLine -match 'kopied\.py') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Service stopped.
