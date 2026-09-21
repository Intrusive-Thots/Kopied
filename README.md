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
- **🔄 Auto-start** — Both services start silently at Windows logon
- **💾 Crash recovery** — Self-healing restart loops keep services running

## 📦 Quick Install

```bat
git clone https://github.com/Intrusive-Thots/Kopied.git
cd Kopied
install.bat
```

The installer will:
1. Copy files to `C:\Kopied\`
2. Install Python dependencies (`pywin32`, `Pillow`)
3. Create Startup shortcuts (auto-start at logon)
4. Create a Desktop shortcut for the viewer
5. Start both services and open the GUI

## 🖥️ GUI Viewer

Open **[http://127.0.0.1:8765](http://127.0.0.1:8765)** or double-click the **Kopied Viewer** Desktop shortcut.

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
│   ├── kopied.py              # Clipboard service (v2.0)
│   ├── kopied_gui.py          # GUI web server (port 8765)
│   ├── launch_kopied.vbs      # Silent launcher with restart loop
│   ├── launch_gui_silent.vbs  # GUI launcher with restart loop
│   ├── install_startup.vbs    # Register at Windows logon
│   ├── stop_kopied.bat        # Stop all services
│   └── verify_kopied.py       # Health check
├── gui\
│   └── index.html             # Web UI (single-page app)
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
:: Start (silent, auto-restarts on crash)
wscript C:\Kopied\bin\launch_kopied.vbs
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

## 🗑️ Uninstall

```bat
powershell -ExecutionPolicy Bypass -File installer\uninstall.ps1
```

## ⚠️ Privacy Notice

**Kopied stores everything you copy**, including passwords, personal messages, and sensitive data. Keep your `C:\Kopied` folder private and exclude it from cloud sync services.

## 📄 License

[MIT](LICENSE) — Free to use, modify, and distribute.
