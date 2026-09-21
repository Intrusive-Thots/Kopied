import os
import sqlite3
import csv
import hashlib
from datetime import datetime

TARGET_BASE = r"C:\Kopied"
INDEX_DB = os.path.join(TARGET_BASE, "index", "seen.sqlite3")
CLIPBOARD_CSV = os.path.join(TARGET_BASE, "clipboard_history.csv")
CLIPBOARD_TEXT_DIR = os.path.join(TARGET_BASE, "Clipboard", "Text")

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8", errors="surrogatepass"))

def main():
    print("Starting historical clipboard text migration...")
    
    if not os.path.exists(INDEX_DB):
        print(f"Index database not found at {INDEX_DB}. Please run the service once first.")
        return
        
    conn = sqlite3.connect(INDEX_DB)
    # Ensure tables exist
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
        CREATE TABLE IF NOT EXISTS clipboard_text_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            hash TEXT NOT NULL,
            content TEXT NOT NULL,
            synced_to_csv INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()

    if not os.path.isdir(CLIPBOARD_TEXT_DIR):
        print(f"No clipboard text directory found at {CLIPBOARD_TEXT_DIR}. Nothing to backfill.")
        return

    files = os.listdir(CLIPBOARD_TEXT_DIR)
    txt_files = sorted([f for f in files if f.startswith("txt_") and f.endswith(".txt")])
    
    if not txt_files:
        print("No text files found to migrate.")
        return

    print(f"Found {len(txt_files)} text files to consolidate.")

    # Append to the CSV. Write header if file is empty or missing.
    write_header = not os.path.exists(CLIPBOARD_CSV) or os.path.getsize(CLIPBOARD_CSV) == 0

    success_count = 0
    skipped_count = 0
    files_to_delete = []

    try:
        with open(CLIPBOARD_CSV, "a", newline="", encoding="utf-8-sig") as csv_f:
            writer = csv.writer(csv_f)
            if write_header:
                writer.writerow(["Date and Time", "Length", "Content"])

            for fname in txt_files:
                # Filename formats:
                # txt_YYYY-MM-DD_HH-MM-SS.txt
                # txt_YYYY-MM-DD_HH-MM-SS_hash.txt
                parts = fname.replace("txt_", "").replace(".txt", "").split("_")
                if len(parts) >= 2:
                    ts_date = parts[0]
                    ts_time = parts[1]
                    timestamp = f"{ts_date}_{ts_time}"
                else:
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

                fpath = os.path.join(CLIPBOARD_TEXT_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except OSError as e:
                    print(f"Failed to read {fname}: {e}")
                    continue

                h = sha256_text(content)

                # Check if already present in database history (to avoid double entry)
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM clipboard_text_history WHERE hash = ? LIMIT 1", (h,))
                in_history = cursor.fetchone()

                if in_history:
                    # Already in SQLite history.
                    skipped_count += 1
                    files_to_delete.append(fpath)
                    continue

                # Add to seen if not present
                try:
                    conn.execute(
                        "INSERT INTO seen(hash, kind, path, first_seen) VALUES (?,?,?,?)",
                        (h, "text", "csv", timestamp.replace("_", " ")),
                    )
                except sqlite3.IntegrityError:
                    pass

                # Save to database queue (mark as synced=1 since we are writing to CSV directly)
                conn.execute(
                    "INSERT INTO clipboard_text_history (timestamp, hash, content, synced_to_csv) VALUES (?,?,?,1)",
                    (timestamp, h, content),
                )
                conn.commit()

                # Write to CSV
                display_ts = timestamp.replace("_", " ")
                writer.writerow([display_ts, len(content), content])
                
                success_count += 1
                files_to_delete.append(fpath)

        print(f"Successfully migrated {success_count} entries to CSV and Database.")
        print(f"Skipped {skipped_count} already consolidated entries.")

        # Verification check: Make sure CSV is written and files can be safely deleted
        if os.path.exists(CLIPBOARD_CSV) and os.path.getsize(CLIPBOARD_CSV) > 0:
            print("Consolidation verified. Cleaning up individual text files to free resources...")
            deleted_count = 0
            for fpath in files_to_delete:
                try:
                    os.remove(fpath)
                    deleted_count += 1
                except OSError as e:
                    print(f"Failed to delete {fpath}: {e}")
            print(f"Cleaned up {deleted_count} files.")
        else:
            print("ERROR: CSV file size is 0 or file missing. Aborting file cleanup.")

    except Exception as e:
        print(f"An error occurred during backfill: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
