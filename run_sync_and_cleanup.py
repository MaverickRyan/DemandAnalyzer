# run_sync_and_cleanup.py
import logging
import subprocess
import sys
import os
import sqlite3
from datetime import datetime, timedelta

# === Settings ===
DB_PATH = "order_log.db"
LOG_DIR = "."  # current directory
DAYS_TO_KEEP = 60

# === Logging Setup ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("combined_sync.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

def run_shipstation_sync():
    logging.info("🚀 Running ShipStation Sync...")
    try:
        subprocess.run(["python", "shipstation_sync.py"], check=True)
        logging.info("✅ ShipStation Sync completed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ ShipStation Sync failed: {e}")

def cleanup_old_orders():
    logging.info("🧹 Cleaning old DB entries...")
    try:
        cutoff = (datetime.now() - timedelta(days=DAYS_TO_KEEP)).isoformat()
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM processed_orders WHERE processed_at < ?", (cutoff,))
        count = cur.fetchone()[0]

        if count > 0:
            cur.execute("DELETE FROM processed_orders WHERE processed_at < ?", (cutoff,))
            conn.commit()
            logging.info(f"✅ Deleted {count} rows older than {DAYS_TO_KEEP} days.")
        else:
            logging.info("📭 No old rows to delete.")
        conn.close()
    except Exception as e:
        logging.error(f"❌ DB cleanup failed: {e}")

def cleanup_old_logs():
    logging.info("🧹 Checking for old .log files...")
    try:
        now = datetime.now()
        for fname in os.listdir(LOG_DIR):
            if fname.endswith(".log"):
                fpath = os.path.join(LOG_DIR, fname)
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                if now - mtime > timedelta(days=DAYS_TO_KEEP):
                    os.remove(fpath)
                    logging.info(f"🗑️ Deleted log file: {fname}")
    except Exception as e:
        logging.error(f"❌ Log file cleanup failed: {e}")

# === Main Execution ===
if __name__ == "__main__":
    run_shipstation_sync()
    cleanup_old_orders()
    cleanup_old_logs()
