"""Health check: process up + unique paste is archived; duplicate is skipped."""
from __future__ import annotations

import os
import subprocess
import sys
import time

LOG = r"C:\Kopied\kopied.log"
TEXT_DIR = r"C:\Kopied\Clipboard\Text"


def list_service() -> str:
    ps = (
        "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object { "
        "$_.Name -match 'python' -and $_.CommandLine -and "
        "$_.CommandLine -match '[\\\\/]bin[\\\\/]kopied\\.py' "
        "} | ForEach-Object { '{0} {1}' -f $_.ProcessId, $_.CommandLine }"
    )
    try:
        return subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            errors="ignore",
            timeout=15,
        ).strip()
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return ""


def set_clip(text: str) -> None:
    import win32clipboard

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def find_text_in_db_and_csv(marker: str) -> tuple[bool, bool]:
    """Checks if the marker is present in SQLite database and CSV.
    Returns (in_db, in_csv).
    """
    in_db = False
    in_csv = False
    
    # 1. Check SQLite DB
    db_path = r"C:\Kopied\index\seen.sqlite3"
    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM clipboard_text_history WHERE content = ? LIMIT 1", (marker,))
            if cursor.fetchone():
                in_db = True
            conn.close()
        except Exception as e:
            print("DB check error:", e)
            
    # 2. Check CSV File
    csv_path = r"C:\Kopied\clipboard_history.csv"
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                content = f.read()
                if marker in content:
                    in_csv = True
        except Exception as e:
            print("CSV check error:", e)
            
    return in_db, in_csv


def main() -> int:
    out = list_service()
    running = bool(out)
    print("--- process ---")
    print(out or "(none)")
    print("running:", running)

    print("--- log tail ---")
    if os.path.exists(LOG):
        with open(LOG, encoding="utf-8", errors="ignore") as f:
            print("".join(f.readlines()[-12:]), end="")

    try:
        import sqlite3
        marker = f"KOPIED_VERIFY_UNIQUE_{int(time.time())}"
        set_clip(marker)
        print(f"--- unique paste: {marker} ---")
        time.sleep(1.5)
        
        in_db, in_csv = find_text_in_db_and_csv(marker)
        if not in_db:
            print("VERIFY FAIL: unique text not found in SQLite database history")
            return 1
        print("VERIFY OK: saved to SQLite database")
        
        if not in_csv:
            print("VERIFY WARNING: unique text not found in CSV (could be expected if CSV is locked)")
        else:
            print("VERIFY OK: synced to CSV spreadsheet")

        # Duplicate check
        db_path = r"C:\Kopied\index\seen.sqlite3"
        conn = sqlite3.connect(db_path)
        before = conn.execute("SELECT COUNT(*) FROM clipboard_text_history").fetchone()[0]
        set_clip(marker)  # exact same content again
        time.sleep(1.5)
        after = conn.execute("SELECT COUNT(*) FROM clipboard_text_history").fetchone()[0]
        conn.close()
        
        if after != before:
            print(f"VERIFY FAIL: duplicate created extra entry in database ({before} -> {after})")
            return 1
        print("VERIFY OK dedup: duplicate paste did not create a new database entry")
    except Exception as e:
        print("clipboard test error:", e)
        return 1

    return 0 if running else 1


if __name__ == "__main__":
    sys.exit(main())
