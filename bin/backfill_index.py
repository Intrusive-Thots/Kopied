"""
One-shot: index existing C:\\Kopied archive files so future runs
dedup against everything already saved (no re-writes).

Safe to re-run. Does not delete or rewrite files.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime

TARGET_BASE = r"C:\Kopied"
TEXT_DIR = os.path.join(TARGET_BASE, "Clipboard", "Text")
IMG_DIR = os.path.join(TARGET_BASE, "Clipboard", "Images")
SS_DIR = os.path.join(TARGET_BASE, "Screenshots")
INDEX_DIR = os.path.join(TARGET_BASE, "index")
INDEX_DB = os.path.join(INDEX_DIR, "seen.sqlite3")

# Source folders — seed path signatures so the service does not re-read them on first start
SOURCE_FOLDERS = [
    os.path.expandvars(
        r"%LOCALAPPDATA%\Packages\MicrosoftWindows.Client.Core_cw5n1h2txyewy\TempState\ScreenClip"
    ),
    os.path.expandvars(
        r"%LOCALAPPDATA%\Packages\Microsoft.ScreenSketch_8wekyb3d8bbwe\TempState"
    ),
    os.path.expandvars(r"%USERPROFILE%\Pictures\Screenshots"),
]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="surrogatepass") as f:
        return hashlib.sha256(f.read().encode("utf-8", errors="surrogatepass")).hexdigest()


def main() -> int:
    os.makedirs(INDEX_DIR, exist_ok=True)
    conn = sqlite3.connect(INDEX_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen (
            hash TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            path TEXT,
            first_seen TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS path_sig (
            path TEXT PRIMARY KEY,
            mtime REAL NOT NULL,
            size INTEGER NOT NULL,
            hash TEXT
        )
        """
    )
    conn.commit()

    added = skipped = errors = 0
    now = datetime.now().isoformat(timespec="seconds")

    jobs = [
        (TEXT_DIR, "text", True),
        (IMG_DIR, "image", False),
        (SS_DIR, "screenshot", False),
    ]

    for folder, kind, is_text in jobs:
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            try:
                h = sha256_text_file(path) if is_text else sha256_file(path)
                try:
                    conn.execute(
                        "INSERT INTO seen(hash, kind, path, first_seen) VALUES (?,?,?,?)",
                        (h, kind, path, now),
                    )
                    added += 1
                except sqlite3.IntegrityError:
                    skipped += 1
            except OSError as e:
                print(f"error {path}: {e}")
                errors += 1
        conn.commit()
        print(f"{kind}: done")

    # Seed source path signatures (stat only — no re-hash) so the live
    # service skips files that already exist at their current mtime/size.
    # Content is already in `seen` via the archive folders above.
    sigs = 0
    for folder in SOURCE_FOLDERS:
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                continue
            path = os.path.join(folder, name)
            try:
                st = os.stat(path)
                conn.execute(
                    """
                    INSERT INTO path_sig(path, mtime, size, hash) VALUES (?,?,?,NULL)
                    ON CONFLICT(path) DO UPDATE SET
                        mtime=excluded.mtime,
                        size=excluded.size
                    """,
                    (path, st.st_mtime, st.st_size),
                )
                sigs += 1
            except OSError:
                errors += 1
        conn.commit()
        print(f"path_sig seeded: {folder}")

    conn.close()
    print(f"added={added} already_indexed={skipped} path_sigs={sigs} errors={errors}")
    print(f"index: {INDEX_DB}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
