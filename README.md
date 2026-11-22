# 📋 Kopied

**Permanent clipboard & screenshot archive for Windows.** Every unique thing you copy is saved forever. Duplicates are never stored twice. Browse everything in a sleek web UI.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078d4.svg)]()
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776ab.svg)](https://python.org)

---

## ✨ Features

- **📝 Text capture** — Every unique text you copy is saved with a timestamp
- **🖼️ Image capture** — Clipboard images (Ctrl+C from anywhere) are saved as PNG
- **📸 Screenshot capture** — Win+Shift+S snips and Win+PrtScn screenshots are auto-archived
- **🔍 Content-level dedup** — SHA-256 hashing ensures no duplicate content is ever stored
- **🌐 Web GUI viewer** — Browse, search, copy, and manage all your clipboard history at `http://127.0.0.1:8765`
- **⚡ Near-zero idle load** — Event-driven clipboard listener, no busy loops
- **🔄 Auto-start** — The clipboard engine runs as a per-user Scheduled Task at logon (`pythonw`, no console)
- **💾 Crash recovery** — The task restarts the engine on failure (up to 999 times, 1 minute apart) and re-checks every 10 minutes if it is not running

## 📦 Quick Install

```bat
git clone https://github.com/Intrusive-Thots/Kopied.git
cd Kopied
install.bat
```

The installer will:
1. Copy files to `C:\Kopied\`
2. Install Python dependencies (`pywin32`, `Pillow`)
3. Register the per-user `Kopied` Scheduled Task (engine auto-start at logon)
4. Create a Desktop shortcut (`Kopied.lnk`) for the viewer, with `assets\kopied.ico`
5. Start the engine and open the GUI

If you already have Kopied at `C:\Kopied` and only need to refresh startup and the shortcut:

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Kopied\bin\install_scheduled_task.ps1
```

## 🖥️ GUI Viewer

Open **[http://127.0.0.1:8765](http://127.0.0.1:8765)** or double-click the **Kopied** Desktop shortcut.

- **Filter** by text, images, or screenshots
- **Search** across all content, filenames, and dates
- **Copy** any item back to your clipboard with one click
- **Delete** items you no longer need
- **Favorite** items to pin them for quick access
- **Keyboard shortcuts**: `/` to search, `Esc` to close, `←`/`→` to navigate

## 🏗️ Architecture

```
C:\Kopied\
├── bin\
│   ├── kopied.py                    # Clipboard service (v2.1)
│   ├── kopied_gui.py                # GUI web server (port 8765)
│   ├── install_scheduled_task.ps1   # Register logon task + Desktop shortcut
│   ├── launch_kopied.vbs            # Optional silent launcher with restart loop
│   ├── launch_gui_silent.vbs        # Optional GUI launcher with restart loop
│   ├── install_startup.vbs          # Legacy Startup-folder registration
│   ├── stop_kopied.bat              # Stop all services
│   └── verify_kopied.py             # Health check
├── assets\
│   ├── kopied.ico                   # Multi-size app icon (16–256)
│   ├── kopied-icon-preview.png      # 256px PNG preview
│   └── make_icon.py                 # Regenerates the icon (needs Pillow)
├── gui\
│   └── index.html                   # Web UI (single-page app)
├── Clipboard\
│   ├── Text\                  # Saved text files
│   └── Images\                # Saved image files
├── Screenshots\               # Captured screenshots
├── index\
│   └── seen.sqlite3           # SHA-256 dedup index (SQLite WAL)
├── clipboard_history.csv      # Consolidated text history spreadsheet
└── kopied.log                 # Activity log
```

| Source | Saved to | Dedup |
|--------|----------|-------|
| Clipboard text | `Clipboard\Text\` + CSV + SQLite | SHA-256 of text |
| Clipboard images | `Clipboard\Images\` | SHA-256 of PNG bytes |
| Win+Shift+S / Snip / Win+PrtScn | `Screenshots\` | SHA-256 of file bytes |

## ⌨️ Commands

```bat
:: Register / refresh the logon task and Desktop shortcut
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Kopied\bin\install_scheduled_task.ps1

:: Start the engine now (after the task is registered)
schtasks /Run /TN Kopied

:: Optional: start the GUI viewer server (silent, auto-restarts on crash)
wscript C:\Kopied\bin\launch_gui_silent.vbs

:: Debug (console output)
py -3 C:\Kopied\bin\kopied.py
py -3 C:\Kopied\bin\kopied_gui.py

:: Health check
py -3 C:\Kopied\bin\verify_kopied.py

:: Stop all
C:\Kopied\bin\stop_kopied.bat
```

## 📋 Dependencies

- **Python 3.10+** with:
  - `pywin32` — Windows clipboard API access
  - `Pillow` — Image processing

```bat
py -3 -m pip install pywin32 Pillow
```


## 🚀 Install / startup (Windows)

The clipboard engine should stay running in the background after you log on. Use a **per-user Scheduled Task** (no admin). Do not also put a Startup-folder shortcut to the engine — that would be a duplicate starter. The engine already refuses a second instance via `kopied.lock` and a global mutex.

1. Keep the app at `C:\Kopied` (adjust paths in `bin\install_scheduled_task.ps1` if you install elsewhere).
2. Dependencies: `py -3 -m pip install pywin32 Pillow`
3. Register or refresh the task and the desktop GUI shortcut:

   ```bat
   powershell -NoProfile -ExecutionPolicy Bypass -File C:\Kopied\bin\install_scheduled_task.ps1
   ```

   The `Kopied` task starts `pythonw.exe` on `bin\kopied.py` at logon (15s delay), restarts on failure up to 999 times one minute apart, has no execution time limit, and runs on battery. A 10-minute repetition trigger starts it again only if it is not already running (`MultipleInstances: IgnoreNew`).

4. The desktop shortcut `Kopied.lnk` opens the web GUI with `pythonw` (no console window) and uses `assets\kopied.ico`. Regenerate the icon with `py -3 C:\Kopied\assets\make_icon.py` if you edit it.

5. Optional: a Startup-folder `Kopied GUI.lnk` can keep the archive viewer server (`bin\kopied_gui.py --no-browser`) listening at logon. That is separate from the engine task.

## 🗑️ Uninstall

```bat
powershell -ExecutionPolicy Bypass -File installer\uninstall.ps1
```

## ⚠️ Privacy Notice

**Kopied stores everything you copy**, including passwords, personal messages, and sensitive data. Keep your `C:\Kopied` folder private and exclude it from cloud sync services.

## 📄 License

[MIT](LICENSE) — Free to use, modify, and distribute.
