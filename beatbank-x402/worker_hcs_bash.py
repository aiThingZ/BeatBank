#!/usr/bin/env python3
"""
BeatBank Worker (HCS -> Bash)
- Poll Hedera Mirror Topic for {"event":"received","job_id","filename"}.
- For each new job:
    * Create isolated work dir: ./jobs_runtime/{job_id}/
    * Copy uploaded file from ./uploads/{job_id}__{filename} -> work/input/{filename}
    * Run your existing bash script (relative paths) inside that work dir
    * Read outputs from work/output/... and work/output_cleaned/...
    * Persist job status in SQLite
    * Optionally publish {"event":"ready"} to Hedera if operator creds exist
      (SKIPPED when DRY_RUN is set)
"""

import os
import sys
import time
import base64
import json
import sqlite3
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict

import httpx
from dotenv import load_dotenv
from colorama import init as colorama_init, Fore, Style

# Optional Hedera publish (if installed and creds provided)
HEDERA_AVAILABLE = False
try:
    from hedera import Client, TopicId, TopicMessageSubmitTransaction, AccountId, PrivateKey  # type: ignore
    HEDERA_AVAILABLE = True
except Exception:
    HEDERA_AVAILABLE = False

# -------- Init --------
colorama_init(autoreset=True)
load_dotenv()

# -------- Config --------
NETWORK = os.getenv("HEDERA_NETWORK", "testnet").lower()
TOPIC_ID = os.getenv("HEDERA_TOPIC_ID")
POLL_INTERVAL_SEC = float(os.getenv("POLL_INTERVAL_SEC", "2"))
STATE_DB = os.getenv("STATE_DB", "beatbank_state.db")

# Where FastAPI server saves uploads:
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "uploads")

# Worker runtime root; each job gets ./jobs_runtime/{job_id}/
JOBS_RUNTIME_ROOT = os.getenv("JOBS_RUNTIME_ROOT", "jobs_runtime")

# Path to your existing bash script (must use relative ./input ./output ./output_cleaned)
STEMS_SCRIPT = os.getenv("STEMS_SCRIPT", "./separate_stems.sh")

# Hedera operator (optional; for publishing "ready")
HEDERA_OPERATOR_ID = os.getenv("HEDERA_OPERATOR_ID")
HEDERA_OPERATOR_KEY = os.getenv("HEDERA_OPERATOR_KEY")

# DRY RUN: if set (non-empty), skip publishing to Hedera
DRY_RUN = bool(os.getenv("DRY_RUN", "").strip())

MIRROR_BASE = {
    "testnet": "https://testnet.mirrornode.hedera.com",
    "previewnet": "https://previewnet.mirrornode.hedera.com",
    "mainnet": "https://mainnet-public.mirrornode.hedera.com",
}.get(NETWORK, "https://testnet.mirrornode.hedera.com")

if not TOPIC_ID:
    print(Fore.RED + "ERROR: HEDERA_TOPIC_ID is required in .env", file=sys.stderr)
    sys.exit(1)

# -------- SQLite --------
SCHEMA = """
CREATE TABLE IF NOT EXISTS hcs_offsets (
    topic_id TEXT PRIMARY KEY,
    last_consensus_ts TEXT,
    last_sequence INTEGER
);
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    status TEXT NOT NULL,           -- received|processing|ready|failed
    upload_path TEXT,
    work_dir TEXT,
    output_vocals TEXT,
    output_vocals_clean TEXT,
    error TEXT
);
"""

@dataclass
class Offset:
    last_consensus_ts: Optional[str]
    last_sequence: Optional[int]

def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(STATE_DB)
    conn.execute("PRAGMA journal_mode=WAL;")
    for stmt in SCHEMA.strip().split(";"):
        s = stmt.strip()
        if s:
            conn.execute(s)
    conn.commit()
    return conn

def load_offset(conn: sqlite3.Connection, topic_id: str) -> Offset:
    cur = conn.execute(
        "SELECT last_consensus_ts, last_sequence FROM hcs_offsets WHERE topic_id = ?",
        (topic_id,),
    )
    row = cur.fetchone()
    if not row:
        return Offset(last_consensus_ts=None, last_sequence=None)
    return Offset(last_consensus_ts=row[0], last_sequence=row[1])

def save_offset(conn: sqlite3.Connection, topic_id: str, ts: str, seq: int) -> None:
    conn.execute(
        """
        INSERT INTO hcs_offsets (topic_id, last_consensus_ts, last_sequence)
        VALUES (?, ?, ?)
        ON CONFLICT(topic_id) DO UPDATE SET
          last_consensus_ts=excluded.last_consensus_ts,
          last_sequence=excluded.last_sequence
        """,
        (topic_id, ts, seq),
    )
    conn.commit()

def job_status(conn: sqlite3.Connection, job_id: str) -> Optional[str]:
    cur = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,))
    row = cur.fetchone()
    return row[0] if row else None

def upsert_job(conn: sqlite3.Connection, job_id: str, **fields) -> None:
    cols = ["job_id"] + list(fields.keys())
    vals = [job_id] + list(fields.values())
    placeholders = ",".join(["?"] * len(vals))
    assignments = ",".join([f"{k}=excluded.{k}" for k in fields.keys()])
    sql = f"""
        INSERT INTO jobs ({",".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(job_id) DO UPDATE SET {assignments}
    """
    conn.execute(sql, vals)
    conn.commit()

# -------- Mirror Node --------
def build_messages_url(topic_id: str, last_ts: Optional[str]) -> str:
    base = f"{MIRROR_BASE}/api/v1/topics/{topic_id}/messages?order=asc&limit=100"
    if last_ts:
        return f"{base}&timestamp=gt:{last_ts}"
    return base

def fetch_page(client: httpx.Client, url: str):
    r = client.get(url, timeout=30.0)
    r.raise_for_status()
    data = r.json()
    messages = data.get("messages", [])
    next_link = data.get("links", {}).get("next")
    if next_link and not next_link.startswith("http"):
        next_link = f"{MIRROR_BASE}{next_link}"
    return messages, next_link

def decode_message(b64: str) -> dict:
    try:
        raw = base64.b64decode(b64)
        try:
            return {"json": json.loads(raw.decode("utf-8"))}
        except Exception:
            return {"text": raw.decode("utf-8", errors="replace")}
    except Exception:
        return {"error": "failed_to_decode_base64"}

# -------- Hedera publisher (optional) --------
def hedera_client() -> Optional["Client"]:
    if not HEDERA_AVAILABLE:
        return None
    if not (HEDERA_OPERATOR_ID and HEDERA_OPERATOR_KEY):
        return None
    def _for_network(net: str):
        if net == "testnet":
            ctor = getattr(Client, "for_testnet", None) or getattr(Client, "forTestnet", None)
        elif net == "previewnet":
            ctor = getattr(Client, "for_previewnet", None) or getattr(Client, "forPreviewnet", None)
        else:
            ctor = getattr(Client, "for_mainnet", None) or getattr(Client, "forMainnet", None)
        return ctor()
    c = _for_network(NETWORK)
    aid = (getattr(AccountId, "fromString", None) or getattr(AccountId, "from_string", None))(HEDERA_OPERATOR_ID)
    pkey = (getattr(PrivateKey, "fromString", None) or getattr(PrivateKey, "from_string", None))(HEDERA_OPERATOR_KEY)
    (getattr(c, "set_operator", None) or getattr(c, "setOperator", None))(aid, pkey)
    return c

def publish_ready(job_id: str, filename: str, walrus_ref: str) -> None:
    # Respect DRY_RUN
    if DRY_RUN:
        print(Fore.YELLOW + f"[publish] DRY_RUN=1 → skipping Hedera publish for job_id={job_id}" + Style.RESET_ALL)
        return

    c = hedera_client()
    if not c:
        print(Fore.YELLOW + "[publish] Skipping Hedera 'ready' publish (no SDK or operator creds).")
        return
    topic = (getattr(TopicId, "fromString", None) or getattr(TopicId, "from_string", None))(TOPIC_ID)
    payload = {
        "event": "ready",
        "job_id": job_id,
        "filename": filename,
        "walrus_ref": walrus_ref,
        "status": "ready",
        "publisher": "beatbank-worker",
        "dry_run": False
    }
    msg = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    tx = TopicMessageSubmitTransaction().setTopicId(topic).setMessage(msg)
    resp = tx.execute(c)
    rcpt = resp.getReceipt(c)
    seq = int(getattr(rcpt, "topicSequenceNumber", 0))
    print(Fore.CYAN + f"[publish] ready → topic={TOPIC_ID} seq={seq} tx={resp.transactionId}" + Style.RESET_ALL)

# -------- Bash script integration --------
def ensure_executable(script_path: str):
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Stem script not found: {script_path}")
    st = os.stat(script_path)
    if not (st.st_mode & 0o111):
        os.chmod(script_path, st.st_mode | 0o111)

def run_stems_script_for_job(source_upload: str, job_id: str, filename: str) -> Tuple[str, str, str]:
    """
    Create job workspace, copy source into ./jobs_runtime/{job_id}/input/,
    run the bash script there, return (work_dir, vocals_path, cleaned_path).
    """
    work_dir = os.path.join(JOBS_RUNTIME_ROOT, job_id)
    input_dir = os.path.join(work_dir, "input")
    output_dir = os.path.join(work_dir, "output")
    cleaned_dir = os.path.join(work_dir, "output_cleaned")

    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(cleaned_dir, exist_ok=True)

    # Copy source file into job's ./input
    base = filename
    stem, _ext = os.path.splitext(base)
    target_in = os.path.join(input_dir, base)
    if os.path.abspath(source_upload) != os.path.abspath(target_in):
        shutil.copy2(source_upload, target_in)

    ensure_executable(STEMS_SCRIPT)

    print(Fore.BLUE + f"[worker] Running stems script in {work_dir}" + Style.RESET_ALL)
    # Run script with cwd=work_dir so its relative ./input ./output etc. match
    env = os.environ.copy()
    subprocess.run([STEMS_SCRIPT], cwd=work_dir, env=env, check=True)

    # Demucs creates: output/htdemucs_ft/{stem}/vocals.wav
    vocals_path = os.path.join(output_dir, "htdemucs_ft", stem, "vocals.wav")
    cleaned_path = os.path.join(cleaned_dir, f"{stem}_vocals_cleaned.wav")

    if not os.path.exists(vocals_path):
        raise FileNotFoundError(f"Expected Demucs output not found: {vocals_path}")
    if not os.path.exists(cleaned_path):
        print(Fore.YELLOW + f"[worker] WARNING: cleaned vocals not found at {cleaned_path} (continuing).")

    return work_dir, vocals_path, cleaned_path

# -------- Main loop --------
def main():
    print(Fore.CYAN + f"[worker] Network={NETWORK}  Topic={TOPIC_ID}  Mirror={MIRROR_BASE}")
    print(Fore.CYAN + f"[worker] State DB={STATE_DB}  Poll every {POLL_INTERVAL_SEC}s")
    print(Fore.CYAN + f"[worker] Uploads dir={UPLOADS_DIR}")
    print(Fore.CYAN + f"[worker] Runtime root={JOBS_RUNTIME_ROOT}")
    print(Fore.CYAN + f"[worker] Stem script={STEMS_SCRIPT}")
    print(Fore.CYAN + f"[worker] DRY_RUN={'1' if DRY_RUN else '0'}")

    conn = db_connect()
    offset = load_offset(conn, TOPIC_ID)
    last_ts = offset.last_consensus_ts
    last_seq = offset.last_sequence
    if last_ts:
        print(Fore.YELLOW + f"[worker] Resuming after ts={last_ts} (seq={last_seq})")
    else:
        print(Fore.YELLOW + "[worker] No prior offset; starting from earliest available")

    url = build_messages_url(TOPIC_ID, last_ts)

    with httpx.Client() as client:
        while True:
            try:
                messages, next_url = fetch_page(client, url)
                if messages:
                    for m in messages:
                        consensus_ts = m.get("consensus_timestamp")
                        seq = m.get("sequence_number")
                        payer = m.get("payer_account_id")  # << who submitted
                        msg_b64 = m.get("message")
                        decoded = decode_message(msg_b64)

                        print(Fore.GREEN + f"[msg] seq={seq} ts={consensus_ts} payer={payer} decoded={decoded}")

                        # Save offset early
                        save_offset(conn, TOPIC_ID, consensus_ts, int(seq))

                        payload = decoded.get("json") if isinstance(decoded, dict) else None
                        if not isinstance(payload, dict):
                            continue

                        # If we see a 'ready' not published by us, make it clear
                        if payload.get("event") == "ready" and payload.get("publisher") != "beatbank-worker":
                            print(Fore.YELLOW + f"[info] READY message observed from another publisher: payer={payer}, payload={payload}")

                        event = payload.get("event")
                        job_id = payload.get("job_id")
                        filename = payload.get("filename")

                        if event != "received" or not job_id or not filename:
                            continue

                        current = job_status(conn, job_id)
                        if current in {"processing", "ready"}:
                            print(Fore.YELLOW + f"[worker] Job {job_id} already {current}; skipping.")
                            continue

                        # resolve upload path
                        source_path = os.path.join(UPLOADS_DIR, f"{job_id}__{filename}")
                        if not os.path.exists(source_path):
                            print(Fore.RED + f"[worker] Upload not found: {source_path}")
                            upsert_job(conn, job_id, filename=filename, status="failed",
                                       upload_path=source_path, error="upload_not_found")
                            continue

                        upsert_job(conn, job_id, filename=filename, status="processing", upload_path=source_path)
                        try:
                            work_dir, vocals_path, cleaned_path = run_stems_script_for_job(source_path, job_id, filename)
                            upsert_job(conn, job_id,
                                       filename=filename,
                                       status="ready",
                                       work_dir=work_dir,
                                       output_vocals=vocals_path,
                                       output_vocals_clean=cleaned_path if os.path.exists(cleaned_path) else None)

                            # Placeholder until you add real Walrus push
                            walrus_ref = f"walrus://beatbank/{job_id}"
                            publish_ready(job_id, filename, walrus_ref)
                            print(Fore.MAGENTA + f"[worker] ✅ Job {job_id} ready.\n"
                                  f"    vocals: {vocals_path}\n"
                                  f"    cleaned: {cleaned_path}")

                        except subprocess.CalledProcessError as e:
                            print(Fore.RED + f"[worker] Stems script failed (job={job_id}) rc={e.returncode}")
                            upsert_job(conn, job_id, filename=filename, status="failed", error=str(e))
                        except Exception as e:
                            print(Fore.RED + f"[worker] Processing error (job={job_id}): {e}")
                            upsert_job(conn, job_id, filename=filename, status="failed", error=str(e))

                    url = next_url or build_messages_url(TOPIC_ID, load_offset(conn, TOPIC_ID).last_consensus_ts)
                else:
                    url = build_messages_url(TOPIC_ID, load_offset(conn, TOPIC_ID).last_consensus_ts)
                    time.sleep(POLL_INTERVAL_SEC)
            except httpx.HTTPStatusError as e:
                print(Fore.RED + f"[worker] HTTP error from mirror node: {e}", file=sys.stderr)
                time.sleep(POLL_INTERVAL_SEC)
            except Exception as e:
                print(Fore.RED + f"[worker] Unexpected error: {e}", file=sys.stderr)
                time.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":
    main()

