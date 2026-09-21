"""
Kopied GUI Server v2.0
Lightweight HTTP server serving the Kopied Archive Web GUI.
Features: optimized preview payloads, text detail endpoint, stats, delete, static serving.
"""

from __future__ import annotations

import json
import mimetypes
import os
import sqlite3
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

TARGET_BASE = r"C:\Kopied"
INDEX_DB = os.path.join(TARGET_BASE, "index", "seen.sqlite3")
GUI_DIR = os.path.join(TARGET_BASE, "gui")
INDEX_HTML = os.path.join(GUI_DIR, "index.html")
PORT = 8765


def _db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(INDEX_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_all_items() -> list[dict]:
    items: list[dict] = []
    if not os.path.exists(INDEX_DB):
        return items

    try:
        conn = _db_conn()
        cursor = conn.cursor()

        # Text history (truncated preview for list performance)
        try:
            rows = cursor.execute(
                "SELECT id, timestamp, hash, content, length(content) "
                "FROM clipboard_text_history ORDER BY id DESC"
            ).fetchall()
            for r in rows:
                content_raw = r[3] or ""
                char_count = r[4] if r[4] is not None else len(content_raw)
                preview = content_raw[:300] if len(content_raw) > 300 else content_raw
                items.append({
                    "id": f"text_{r[0]}",
                    "db_id": r[0],
                    "kind": "text",
                    "timestamp": r[1],
                    "hash": r[2],
                    "preview": preview,
                    "is_truncated": len(content_raw) > 300,
                    "char_count": char_count,
                    "path": "",
                    "filename": ""
                })
        except sqlite3.Error:
            pass

        # Images and screenshots from seen table
        try:
            rows = cursor.execute(
                "SELECT rowid, hash, kind, path, first_seen FROM seen "
                "WHERE kind IN ('image', 'screenshot') ORDER BY rowid DESC"
            ).fetchall()
            for r in rows:
                p = r[3] or ""
                fname = os.path.basename(p) if p else ""
                raw_ts = r[4] or ""
                clean_ts = raw_ts.replace("T", "_").replace(":", "-")
                if len(clean_ts) > 19:
                    clean_ts = clean_ts[:19]

                items.append({
                    "id": f"{r[2]}_{r[0]}",
                    "db_id": r[0],
                    "kind": r[2],
                    "timestamp": clean_ts,
                    "hash": r[1],
                    "preview": "",
                    "is_truncated": False,
                    "char_count": 0,
                    "path": p,
                    "filename": fname
                })
        except sqlite3.Error:
            pass

        conn.close()
    except Exception as e:
        print(f"Error reading database: {e}", file=sys.stderr)

    items.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return items


def get_text_detail(db_id: int) -> str:
    if not os.path.exists(INDEX_DB):
        return ""
    try:
        conn = _db_conn()
        row = conn.execute(
            "SELECT content FROM clipboard_text_history WHERE id = ? LIMIT 1",
            (db_id,)
        ).fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception:
        return ""


def get_stats() -> dict:
    stats = {
        "total": 0, "text_count": 0, "image_count": 0,
        "screenshot_count": 0, "disk_usage_mb": 0.0,
        "newest": "", "oldest": ""
    }
    if not os.path.exists(INDEX_DB):
        return stats

    try:
        conn = _db_conn()

        # Text count
        row = conn.execute("SELECT count(*) FROM clipboard_text_history").fetchone()
        stats["text_count"] = row[0] if row else 0

        # Image/screenshot counts
        row = conn.execute("SELECT count(*) FROM seen WHERE kind='image'").fetchone()
        stats["image_count"] = row[0] if row else 0
        row = conn.execute("SELECT count(*) FROM seen WHERE kind='screenshot'").fetchone()
        stats["screenshot_count"] = row[0] if row else 0

        stats["total"] = stats["text_count"] + stats["image_count"] + stats["screenshot_count"]

        # Date range from text history
        row = conn.execute("SELECT max(timestamp), min(timestamp) FROM clipboard_text_history").fetchone()
        if row and row[0]:
            stats["newest"] = row[0]
            stats["oldest"] = row[1]

        conn.close()

        # Disk usage: sum up files in Clipboard/ and Screenshots/ dirs
        total_bytes = 0
        for dirpath, _, filenames in os.walk(os.path.join(TARGET_BASE, "Clipboard")):
            for f in filenames:
                try:
                    total_bytes += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
        for dirpath, _, filenames in os.walk(os.path.join(TARGET_BASE, "Screenshots")):
            for f in filenames:
                try:
                    total_bytes += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
        # Also add the CSV and SQLite
        for extra in ["clipboard_history.csv", os.path.join("index", "seen.sqlite3")]:
            fp = os.path.join(TARGET_BASE, extra)
            if os.path.exists(fp):
                total_bytes += os.path.getsize(fp)

        stats["disk_usage_mb"] = round(total_bytes / (1024 * 1024), 1)

    except Exception as e:
        print(f"Error computing stats: {e}", file=sys.stderr)

    return stats


def delete_item(item_id: str) -> bool:
    """Delete an item by its composite ID (e.g., 'text_42' or 'image_7')."""
    if not os.path.exists(INDEX_DB):
        return False

    try:
        conn = _db_conn()

        if item_id.startswith("text_"):
            db_id = int(item_id[5:])
            conn.execute("DELETE FROM clipboard_text_history WHERE id = ?", (db_id,))
            conn.commit()
            conn.close()
            return True

        elif item_id.startswith("image_") or item_id.startswith("screenshot_"):
            parts = item_id.split("_", 1)
            kind = parts[0]
            rowid = int(parts[1])

            # Get the file path before deleting
            row = conn.execute("SELECT path FROM seen WHERE rowid = ? AND kind = ?", (rowid, kind)).fetchone()
            conn.execute("DELETE FROM seen WHERE rowid = ? AND kind = ?", (rowid, kind))
            conn.commit()
            conn.close()

            # Delete the file from disk
            if row and row[0] and os.path.exists(row[0]):
                try:
                    os.remove(row[0])
                except OSError:
                    pass
            return True

        conn.close()
    except Exception as e:
        print(f"Error deleting item {item_id}: {e}", file=sys.stderr)

    return False


class KopiedGUIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath, mime=None):
        if not os.path.exists(filepath) or not os.path.isfile(filepath):
            self.send_error(404, "File not found")
            return
        if not mime:
            mime, _ = mimetypes.guess_type(filepath)
            if not mime:
                mime = "application/octet-stream"
        try:
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(content)
        except OSError as e:
            self.send_error(500, f"Error reading file: {e}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/items":
            self._send_json(get_all_items())
            return

        if path == "/api/stats":
            self._send_json(get_stats())
            return

        if path == "/api/text_detail":
            params = urllib.parse.parse_qs(parsed.query)
            item_id_str = params.get("id", [""])[0]
            if item_id_str.startswith("text_"):
                item_id_str = item_id_str[5:]
            content = ""
            if item_id_str.isdigit():
                content = get_text_detail(int(item_id_str))
            self._send_json({"id": item_id_str, "content": content})
            return

        if path == "/api/media":
            params = urllib.parse.parse_qs(parsed.query)
            file_path = params.get("path", [""])[0]
            file_path = os.path.abspath(file_path)
            self._send_file(file_path)
            return

        # Serve static files from gui/ directory
        if path == "/" or path == "/index.html":
            self._send_file(INDEX_HTML, "text/html; charset=utf-8")
            return

        # Serve other static assets from gui/ (CSS, JS, images, etc.)
        if path.startswith("/static/"):
            safe_path = os.path.normpath(os.path.join(GUI_DIR, path[8:]))
            if safe_path.startswith(GUI_DIR):
                self._send_file(safe_path)
                return

        self.send_error(404, "Not Found")

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/items/"):
            item_id = path[len("/api/items/"):]
            item_id = urllib.parse.unquote(item_id)
            if delete_item(item_id):
                self._send_json({"status": "deleted", "id": item_id})
            else:
                self._send_json({"status": "error", "message": "Item not found"}, 404)
            return

        self.send_error(404, "Not Found")


def run_server(open_browser: bool = True):
    server_address = ("127.0.0.1", PORT)
    httpd = HTTPServer(server_address, KopiedGUIHandler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Kopied GUI Server v2.0 running at {url}")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Kopied GUI Server.")
        httpd.server_close()


if __name__ == "__main__":
    no_browser = "--no-browser" in sys.argv or "--test" in sys.argv
    run_server(open_browser=not no_browser)
