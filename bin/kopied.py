"""
Kopied Service v2.0
-------------------
Permanent clipboard + screenshot archive with content-level dedup.

Goals:
  - Keep every unique text/image you ever copy (and snips/screenshots)
  - Never store the same content twice (SHA-256 index)
  - Stay nearly idle when the clipboard is quiet (event-driven, not busy-poll)

Layout:
  C:\\Kopied\\Clipboard\\Text\\txt_YYYY-MM-DD_HH-MM-SS_<hash8>.txt
  C:\\Kopied\\Clipboard\\Images\\img_YYYY-MM-DD_HH-MM-SS_<hash8>.png
  C:\\Kopied\\Screenshots\\ss_YYYY-MM-DD_HH-MM-SS_<hash8>.png
  C:\\Kopied\\index\\seen.sqlite3   — hash index (tiny, O(1) dedup)
  C:\\Kopied\\kopied.log
"""

from __future__ import annotations

import csv
import ctypes
import hashlib
import os
import shutil
import sqlite3
import sys
import threading
import time
import traceback
from ctypes import wintypes
from datetime import datetime
from io import BytesIO
from typing import Optional

import win32clipboard
# PIL (Pillow) is imported lazily inside _save_image to conserve idle RAM


# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------
TARGET_BASE = r"C:\Kopied"
LOG_FILE = os.path.join(TARGET_BASE, "kopied.log")
SCREENSHOTS_DIR = os.path.join(TARGET_BASE, "Screenshots")
CLIPBOARD_TEXT_DIR = os.path.join(TARGET_BASE, "Clipboard", "Text")
CLIPBOARD_IMAGES_DIR = os.path.join(TARGET_BASE, "Clipboard", "Images")
CLIPBOARD_CSV = os.path.join(TARGET_BASE, "clipboard_history.csv")
INDEX_DIR = os.path.join(TARGET_BASE, "index")
INDEX_DB = os.path.join(INDEX_DIR, "seen.sqlite3")
LOCK_PATH = os.path.join(TARGET_BASE, "kopied.lock")

# Screenshot sources (only watched if the folder already exists)
SCREENCLIP_PATH = os.path.expandvars(
    r"%LOCALAPPDATA%\Packages\MicrosoftWindows.Client.Core_cw5n1h2txyewy\TempState\ScreenClip"
)
SCREENSKETCH_PATH = os.path.expandvars(
    r"%LOCALAPPDATA%\Packages\Microsoft.ScreenSketch_8wekyb3d8bbwe\TempState"
)
# Win+PrtScn — watched for new files only; no bulk re-import every boot
PICTURES_SCREENSHOTS = os.path.expandvars(r"%USERPROFILE%\Pictures\Screenshots")

VERSION = "2.1"


# Fallback poll if the message-listener path is unavailable (seconds).
# 2.0s is plenty: sequence number is a single integer compare.
FALLBACK_POLL_S = 2.0

# Screenshot folder scan interval when using the lightweight scanner
# (no watchdog thread storm). Only stats mtimes — very cheap.
SCREEN_SCAN_S = 5.0

# Skip empty / whitespace-only clipboard text
MIN_TEXT_LEN = 1

# Max text we will archive (chars). Larger pastes are still hashed fully
# but we refuse absurd multi-megabyte dumps that aren't real clipboard use.
MAX_TEXT_CHARS = 5_000_000

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_CLIPBOARDUPDATE = 0x031D
WM_DESTROY = 0x0002
HWND_MESSAGE = wintypes.HWND(-3)  # message-only window (no UI)

try:
    user32.AddClipboardFormatListener.argtypes = [wintypes.HWND]
    user32.AddClipboardFormatListener.restype = wintypes.BOOL
    user32.RemoveClipboardFormatListener.argtypes = [wintypes.HWND]
    user32.RemoveClipboardFormatListener.restype = wintypes.BOOL
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = wintypes.LPARAM
    _HAS_CLIP_LISTENER = True
except AttributeError:
    _HAS_CLIP_LISTENER = False


# ---------------------------------------------------------------------------
# Logging (append-only, no flush thrash)
# ---------------------------------------------------------------------------
MAX_LOG_SIZE = 2 * 1024 * 1024  # 2MB
_log_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    with _log_lock:
        try:
            if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
                old_file = LOG_FILE + ".old"
                if os.path.exists(old_file):
                    try:
                        os.remove(old_file)
                    except OSError:
                        pass
                try:
                    os.rename(LOG_FILE, old_file)
                except OSError:
                    pass
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass



def ensure_dirs() -> None:
    for d in (SCREENSHOTS_DIR, CLIPBOARD_TEXT_DIR, CLIPBOARD_IMAGES_DIR, INDEX_DIR):
        os.makedirs(d, exist_ok=True)


# ---------------------------------------------------------------------------
# Dedup index (SQLite, WAL — survives restarts, O(1) lookups)
# ---------------------------------------------------------------------------
class SeenIndex:
    """Tracks content hashes so we never write the same payload twice."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                hash TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                path TEXT,
                first_seen TEXT NOT NULL
            )
            """
        )
        # Path signatures: avoid re-reading screenshot sources we've already scanned
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS path_sig (
                path TEXT PRIMARY KEY,
                mtime REAL NOT NULL,
                size INTEGER NOT NULL,
                hash TEXT
            )
            """
        )
        # Text history table: database queue for CSV synchronization
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clipboard_text_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hash TEXT NOT NULL,
                content TEXT NOT NULL,
                synced_to_csv INTEGER DEFAULT 0
            )
            """
        )
        self._conn.commit()
        # In-memory set of recently seen hashes for the hot path (bounded to 10k for tiny RAM).
        # Full history still lives in SQLite for cold lookups.
        self._hot: set[str] = set()
        self._path_sig: dict[str, tuple[float, int]] = {}
        self._has_unsynced_text: bool = False
        self._load_hot()
        self._load_path_sigs()
        self._check_initial_unsynced()

    def _load_hot(self) -> None:
        """Load a bounded hot set (last ~10k hashes) so restarts stay fast and RAM low."""
        try:
            rows = self._conn.execute(
                "SELECT hash FROM seen ORDER BY rowid DESC LIMIT 10000"
            ).fetchall()
            self._hot = {r[0] for r in rows}
        except sqlite3.Error:
            self._hot = set()

    def _check_initial_unsynced(self) -> None:
        try:
            row = self._conn.execute(
                "SELECT 1 FROM clipboard_text_history WHERE synced_to_csv = 0 LIMIT 1"
            ).fetchone()
            self._has_unsynced_text = bool(row)
        except sqlite3.Error:
            self._has_unsynced_text = True

    def _load_path_sigs(self) -> None:
        try:
            rows = self._conn.execute(
                "SELECT path, mtime, size FROM path_sig"
            ).fetchall()
            self._path_sig = {r[0]: (r[1], r[2]) for r in rows}
        except sqlite3.Error:
            self._path_sig = {}

    def known(self, h: str) -> bool:
        if h in self._hot:
            return True
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM seen WHERE hash=? LIMIT 1", (h,)
            ).fetchone()
            if row:
                self._hot.add(h)
                return True
        return False

    def remember(self, h: str, kind: str, path: str) -> bool:
        """
        Record hash. Returns True if this is the first time we've seen it
        (caller should write the file). Returns False if already known.
        """
        if h in self._hot:
            return False
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO seen(hash, kind, path, first_seen) VALUES (?,?,?,?)",
                    (h, kind, path, datetime.now().isoformat(timespec="seconds")),
                )
                self._conn.commit()
                self._hot.add(h)
                # Bound hot set memory to 10,000 items (~800KB)
                if len(self._hot) > 12_000:
                    self._hot = set(list(self._hot)[-8_000:])
                return True
            except sqlite3.IntegrityError:
                self._hot.add(h)
                return False


    def path_unchanged(self, path: str, mtime: float, size: int) -> bool:
        """True if we already scanned this path at this mtime+size (skip I/O)."""
        prev = self._path_sig.get(path)
        if prev is None:
            return False
        return prev[0] == mtime and prev[1] == size

    def note_path(self, path: str, mtime: float, size: int, content_hash: Optional[str] = None) -> None:
        self._path_sig[path] = (mtime, size)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO path_sig(path, mtime, size, hash) VALUES (?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET
                    mtime=excluded.mtime,
                    size=excluded.size,
                    hash=excluded.hash
                """,
                (path, mtime, size, content_hash),
            )
            self._conn.commit()

    def save_text_history(self, timestamp: str, h: str, text: str) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO clipboard_text_history (timestamp, hash, content, synced_to_csv) VALUES (?,?,?,0)",
                    (timestamp, h, text),
                )
                self._conn.commit()
                self._has_unsynced_text = True
            except sqlite3.Error as e:
                log(f"Database error saving text history: {e}")

    def get_unsynced_text(self) -> list[tuple[int, str, str]]:
        with self._lock:
            try:
                return self._conn.execute(
                    "SELECT id, timestamp, content FROM clipboard_text_history WHERE synced_to_csv = 0 ORDER BY id ASC"
                ).fetchall()
            except sqlite3.Error as e:
                log(f"Database error fetching unsynced text: {e}")
                return []

    def mark_text_synced(self, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock:
            try:
                placeholders = ",".join("?" for _ in ids)
                self._conn.execute(
                    f"UPDATE clipboard_text_history SET synced_to_csv = 1 WHERE id IN ({placeholders})",
                    tuple(ids),
                )
                self._conn.commit()
            except sqlite3.Error as e:
                log(f"Database error marking text synced: {e}")

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8", errors="surrogatepass"))


def sync_to_csv(index: SeenIndex) -> bool:
    """Tries to write unsynced text history from SQLite to the CSV file.
    Returns True if successful, False if blocked/failed.
    """
    if not index._has_unsynced_text:
        return True

    unsynced = index.get_unsynced_text()
    if not unsynced:
        index._has_unsynced_text = False
        return True

    write_header = not os.path.exists(CLIPBOARD_CSV) or os.path.getsize(CLIPBOARD_CSV) == 0

    try:
        with open(CLIPBOARD_CSV, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["Date and Time", "Length", "Content"])
            
            ids_to_mark = []
            for row in unsynced:
                db_id, timestamp, content = row
                display_ts = timestamp.replace("_", " ")
                writer.writerow([display_ts, len(content), content])
                ids_to_mark.append(db_id)
            
            if ids_to_mark:
                index.mark_text_synced(ids_to_mark)
                index._has_unsynced_text = False
        return True
    except OSError as e:
        log(f"CSV Sync skipped (file may be open/locked): {e}")
        return False



# ---------------------------------------------------------------------------
# Clipboard capture
# ---------------------------------------------------------------------------
class ClipboardArchive:
    def __init__(self, index: SeenIndex) -> None:
        self.index = index
        self._last_text_hash: Optional[str] = None
        self._last_img_hash: Optional[str] = None
        self._busy = threading.Lock()

    def on_change(self) -> None:
        # Serialize captures; ignore nested/re-entrant clipboard noise
        if not self._busy.acquire(blocking=False):
            return
        try:
            self._capture()
        finally:
            self._busy.release()

    def _capture(self) -> None:
        text: Optional[str] = None
        has_image = False

        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    raw = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                    if isinstance(raw, str):
                        text = raw
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_DIB):
                    has_image = True
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
            return

        if text is not None:
            self._save_text(text)

        if has_image:
            self._save_image()

    def _save_text(self, text: str) -> None:
        if not text or len(text.strip()) < MIN_TEXT_LEN:
            return
        if len(text) > MAX_TEXT_CHARS:
            log(f"Skipped oversized text paste ({len(text)} chars)")
            return

        h = sha256_text(text)
        if h == self._last_text_hash:
            return  # same as last event — OS often re-fires
        self._last_text_hash = h

        if self.index.known(h):
            return  # already archived sometime in the past

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        if not self.index.remember(h, "text", "csv"):
            return
        try:
            self.index.save_text_history(ts, h, text)
            log(f"Saved text to database queue ({len(text)} chars)")
        except Exception as e:
            log(f"Error saving to database queue: {e}")

        # Try to sync immediately
        sync_to_csv(self.index)

    def _save_image(self) -> None:
        try:
            from PIL import Image, ImageGrab
            img = ImageGrab.grabclipboard()
            if not isinstance(img, Image.Image):
                return

            # Fast check: if size & mode match last image, check raw sample to avoid expensive PNG encoding
            raw_meta = (img.size, img.mode)
            if hasattr(self, "_last_raw_meta") and self._last_raw_meta == raw_meta:
                raw_bytes = img.tobytes()
                raw_hash = hashlib.sha256(raw_bytes).hexdigest()
                if hasattr(self, "_last_raw_hash") and self._last_raw_hash == raw_hash:
                    return
                self._last_raw_hash = raw_hash
            else:
                self._last_raw_meta = raw_meta
                self._last_raw_hash = hashlib.sha256(img.tobytes()).hexdigest()

            # Normalize to PNG bytes
            buf = BytesIO()
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            # compress_level=1 is ~10x faster than optimize=True and avoids CPU spikes
            img.save(buf, format="PNG", compress_level=1)
            data = buf.getvalue()
        except Exception as e:
            log(f"Error reading clipboard image: {e}")
            return

        h = sha256_bytes(data)
        if h == self._last_img_hash:
            return
        self._last_img_hash = h

        if self.index.known(h):
            return

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"img_{ts}_{h[:8]}.png"
        path = os.path.join(CLIPBOARD_IMAGES_DIR, filename)

        if not self.index.remember(h, "image", path):
            return
        try:
            with open(path, "wb") as f:
                f.write(data)
            log(f"Saved image {filename} ({len(data)} bytes)")
        except OSError as e:
            log(f"Error saving image: {e}")



# ---------------------------------------------------------------------------
# Screenshot archive (content-hash dedup, mtime-based light scan)
# ---------------------------------------------------------------------------
class ScreenshotArchive:
    """
    Watches screenshot folders by cheap mtime/size polling (no watchdog).
    Idle cost: listdir + stat only. Full file reads only for brand-new files.
    """

    def __init__(self, index: SeenIndex) -> None:
        self.index = index
        self._paths = [
            p
            for p in (SCREENCLIP_PATH, SCREENSKETCH_PATH, PICTURES_SCREENSHOTS)
            if os.path.isdir(p)
        ]
        self._folder_mtimes: dict[str, float] = {}

    def scan_once(self) -> None:
        for folder in self._paths:
            try:
                folder_mtime = os.stat(folder).st_mtime
            except OSError:
                continue

            # If folder mtime has not changed, no files were added or removed
            if self._folder_mtimes.get(folder) == folder_mtime:
                continue

            try:
                names = os.listdir(folder)
                self._folder_mtimes[folder] = folder_mtime
            except OSError:
                continue

            for name in names:
                if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                    continue
                src = os.path.join(folder, name)
                try:
                    st = os.stat(src)
                except OSError:
                    continue
                if self.index.path_unchanged(src, st.st_mtime, st.st_size):
                    continue
                self._import_file(src, st.st_mtime, st.st_size)


    def _import_file(self, src: str, mtime: float, size: int) -> None:
        # Brief wait only if file looks brand-new (still being written)
        age = time.time() - mtime
        if age < 2.0:
            try:
                time.sleep(0.2)
                st2 = os.stat(src)
                mtime, size = st2.st_mtime, st2.st_size
                if self.index.path_unchanged(src, mtime, size):
                    return
            except OSError:
                return

        try:
            with open(src, "rb") as f:
                data = f.read()
        except OSError as e:
            log(f"Error reading screenshot {src}: {e}")
            return

        if not data:
            self.index.note_path(src, mtime, size, None)
            return

        h = sha256_bytes(data)
        # Always record path sig so we never re-read this version
        self.index.note_path(src, mtime, size, h)

        if self.index.known(h):
            return

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        ext = os.path.splitext(src)[1].lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            ext = ".png"
        filename = f"ss_{ts}_{h[:8]}{ext}"
        dest = os.path.join(SCREENSHOTS_DIR, filename)

        if not self.index.remember(h, "screenshot", dest):
            return
        try:
            shutil.copy2(src, dest)
            log(f"Saved screenshot {filename}")
        except OSError as e:
            log(f"Error saving screenshot: {e}")


# ---------------------------------------------------------------------------
# Event-driven clipboard loop (zero work while idle)
# ---------------------------------------------------------------------------
class ClipboardListener:
    """
    Uses AddClipboardFormatListener + a message-only window.
    The thread blocks in GetMessage — no CPU until the clipboard changes.
    Falls back to sequence-number polling if the listener can't start.
    """

    def __init__(self, archive: ClipboardArchive) -> None:
        self.archive = archive
        self._stop = threading.Event()
        self._stop_event = kernel32.CreateEventW(None, True, False, None)

    def stop(self) -> None:
        self._stop.set()
        if getattr(self, "_stop_event", None):
            kernel32.SetEvent(self._stop_event)

    def run(self) -> None:
        if _HAS_CLIP_LISTENER and self._run_listener():
            return
        log("Clipboard listener unavailable; using low-rate poll fallback")
        self._run_poll()

    def _run_poll(self) -> None:
        last_seq = -1
        while not self._stop.is_set():
            try:
                seq = win32clipboard.GetClipboardSequenceNumber()
                if seq != last_seq:
                    last_seq = seq
                    self.archive.on_change()
            except Exception:
                pass
            self._stop.wait(FALLBACK_POLL_S)

    def _run_listener(self) -> bool:
        # Window procedure
        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )

        def _wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_CLIPBOARDUPDATE:
                try:
                    self.archive.on_change()
                except Exception as e:
                    log(f"Clipboard capture error: {e}")
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        wndproc = WNDPROC(_wndproc)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [
                ("style", ctypes.c_uint),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        hinst = kernel32.GetModuleHandleW(None)
        class_name = "KopiedClipboardSink"
        wc = WNDCLASS()
        wc.style = 0
        wc.lpfnWndProc = wndproc
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinst
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = class_name

        atom = user32.RegisterClassW(ctypes.byref(wc))
        if not atom:
            # Class may already exist from a previous run in same process
            err = kernel32.GetLastError()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                log(f"RegisterClassW failed: {err}")
                return False

        hwnd = user32.CreateWindowExW(
            0,
            class_name,
            "Kopied",
            0,
            0,
            0,
            0,
            0,
            HWND_MESSAGE,
            None,
            hinst,
            None,
        )
        if not hwnd:
            log(f"CreateWindowExW failed: {kernel32.GetLastError()}")
            return False

        if not user32.AddClipboardFormatListener(hwnd):
            log(f"AddClipboardFormatListener failed: {kernel32.GetLastError()}")
            user32.DestroyWindow(hwnd)
            return False

        log("Clipboard listener active (event-driven, zero wakeups when idle)")

        # Capture whatever is currently on the clipboard once at start
        try:
            self.archive.on_change()
        except Exception as e:
            log(f"Initial clipboard capture error: {e}")

        # Pump messages with zero idle wakeups using Win32 event wait
        msg = wintypes.MSG()
        handles = (wintypes.HANDLE * 1)(self._stop_event)
        INFINITE = 0xFFFFFFFF
        QS_ALLINPUT = 0x04FF

        while not self._stop.is_set():
            ret = user32.MsgWaitForMultipleObjects(
                1, handles, False, INFINITE, QS_ALLINPUT
            )
            if ret == 0:  # _stop_event signaled
                break

            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE=1
                if msg.message == 0x0012:  # WM_QUIT
                    self._stop.set()
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        try:
            user32.RemoveClipboardFormatListener(hwnd)
        except Exception:
            pass
        user32.DestroyWindow(hwnd)
        if getattr(self, "_stop_event", None):
            kernel32.CloseHandle(self._stop_event)
            self._stop_event = None
        return True



# ---------------------------------------------------------------------------
# Single-instance lock
# ---------------------------------------------------------------------------
_lock_fh = None
_mutex_handle = None


def acquire_single_instance() -> bool:
    global _lock_fh, _mutex_handle
    # 1. Named Win32 Mutex (kernel-level, automatically freed if process crashes)
    try:
        ERROR_ALREADY_EXISTS = 183
        _mutex_handle = kernel32.CreateMutexW(None, False, "Global\\Kopied_Singleton_Mutex")
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return False
    except Exception:
        pass

    # 2. File lock with explicit seek(0)
    try:
        import msvcrt
        _lock_fh = open(LOCK_PATH, "a+", encoding="utf-8")
        _lock_fh.seek(0)
        msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_fh.seek(0)
        _lock_fh.truncate()
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
        return True
    except OSError:
        return False
    except ImportError:
        return True



# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_service() -> None:
    ensure_dirs()
    log(f"Kopied Service v{VERSION} started. Base={TARGET_BASE} pid={os.getpid()}")

    index = SeenIndex(INDEX_DB)
    clipboard = ClipboardArchive(index)
    screenshots = ScreenshotArchive(index)

    # Clipboard first — never block pastes behind screenshot I/O
    listener = ClipboardListener(clipboard)
    t = threading.Thread(target=listener.run, name="clipboard", daemon=True)
    t.start()

    if screenshots._paths:
        for p in screenshots._paths:
            log(f"Screenshot source: {p}")
    else:
        log("No screenshot source folders found (clipboard-only mode)")

    try:
        while True:
            # Lightweight scan: listdir+stat only for known files; rare reads for new ones
            try:
                screenshots.scan_once()
            except Exception as e:
                log(f"Screenshot scan error: {e}")
            # Periodic CSV sync retry (in case it was locked by Excel)
            try:
                sync_to_csv(index)
            except Exception as e:
                log(f"CSV periodic sync error: {e}")
            time.sleep(SCREEN_SCAN_S)
    except KeyboardInterrupt:
        log("Shutting down...")
    finally:
        listener.stop()
        index.close()


if __name__ == "__main__":
    ensure_dirs()
    if not acquire_single_instance():
        # Already running — silent exit, no log spam
        sys.exit(0)
    
    while True:
        try:
            run_service()
        except Exception as e:
            log(f"FATAL: {e}")
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(traceback.format_exc() + "\n")
            except OSError:
                pass
        log("Service crash detected. Restarting in 5 seconds...")
        time.sleep(5)
