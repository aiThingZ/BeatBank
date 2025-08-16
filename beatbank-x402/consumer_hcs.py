#!/usr/bin/env python3
"""
BeatBank Hedera HCS Consumer (mirror node poller with color output)
"""

import os
import sys
import time
import base64
import json
import sqlite3
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict

import httpx
from dotenv import load_dotenv
from colorama import init as colorama_init, Fore, Style

# -------- Init color --------
colorama_init(autoreset=True)

# -------- Config --------
load_dotenv()

NETWORK = os.getenv("HEDERA_NETWORK", "testnet").lower()
TOPIC_ID = os.getenv("HEDERA_TOPIC_ID")
POLL_INTERVAL_SEC = float(os.getenv("POLL_INTERVAL_SEC", "2"))
STATE_DB = os.getenv("STATE_DB", "beatbank_state.db")

MIRROR_BASE = {
    "testnet": "https://testnet.mirrornode.hedera.com",
    "previewnet": "https://previewnet.mirrornode.hedera.com",
    "mainnet": "https://mainnet-public.mirrornode.hedera.com",
}.get(NETWORK, "https://testnet.mirrornode.hedera.com")

if not TOPIC_ID:
    print(Fore.RED + "ERROR: HEDERA_TOPIC_ID is required in .env", file=sys.stderr)
    sys.exit(1)

# -------- Persistence (SQLite) --------
SCHEMA = """
CREATE TABLE IF NOT EXISTS hcs_offsets (
    topic_id TEXT PRIMARY KEY,
    last_consensus_ts TEXT,
    last_sequence INTEGER
);
"""

@dataclass
class Offset:
    last_consensus_ts: Optional[str]
    last_sequence: Optional[int]

def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(STATE_DB)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(SCHEMA)
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

# -------- Mirror Node client --------
def build_messages_url(topic_id: str, last_ts: Optional[str]) -> str:
    base = f"{MIRROR_BASE}/api/v1/topics/{topic_id}/messages?order=asc&limit=100"
    if last_ts:
        return f"{base}&timestamp=gt:{last_ts}"
    return base

def fetch_page(client: httpx.Client, url: str) -> Tuple[List[Dict], Optional[str]]:
    r = client.get(url, timeout=30.0)
    r.raise_for_status()
    data = r.json()
    messages = data.get("messages", [])
    next_link = data.get("links", {}).get("next")
    if next_link and not next_link.startswith("http"):
        next_link = f"{MIRROR_BASE}{next_link}"
    return messages, next_link

def decode_message(b64: str) -> Optional[dict]:
    try:
        raw = base64.b64decode(b64)
        try:
            return {"json": json.loads(raw.decode("utf-8"))}
        except Exception:
            return {"text": raw.decode("utf-8", errors="replace")}
    except Exception:
        return {"error": "failed_to_decode_base64"}

# -------- Main loop --------
def main():
    print(Fore.CYAN + f"[consumer] Network={NETWORK}  Topic={TOPIC_ID}  Mirror={MIRROR_BASE}")
    print(Fore.CYAN + f"[consumer] State DB={STATE_DB}  Poll every {POLL_INTERVAL_SEC}s")

    conn = db_connect()
    offset = load_offset(conn, TOPIC_ID)
    last_ts = offset.last_consensus_ts
    last_seq = offset.last_sequence

    if last_ts:
        print(Fore.YELLOW + f"[consumer] Resuming after ts={last_ts} (seq={last_seq})")
    else:
        print(Fore.YELLOW + "[consumer] No prior offset; starting from earliest available")

    url = build_messages_url(TOPIC_ID, last_ts)

    with httpx.Client() as client:
        while True:
            try:
                messages, next_url = fetch_page(client, url)
                if messages:
                    for m in messages:
                        consensus_ts = m.get("consensus_timestamp")
                        seq = m.get("sequence_number")
                        payer = m.get("payer_account_id")
                        msg_b64 = m.get("message")
                        decoded = decode_message(msg_b64)

                        detail = {
                            "sequence": seq,
                            "consensus_timestamp": consensus_ts,
                            "payer": payer,
                            "decoded": decoded,
                        }
                        print(Fore.GREEN + f"Got message: {json.dumps(detail, separators=(',',':'))}")

                        save_offset(conn, TOPIC_ID, consensus_ts, int(seq))

                    url = next_url or build_messages_url(
                        TOPIC_ID, load_offset(conn, TOPIC_ID).last_consensus_ts
                    )
                else:
                    url = build_messages_url(
                        TOPIC_ID, load_offset(conn, TOPIC_ID).last_consensus_ts
                    )
                    time.sleep(POLL_INTERVAL_SEC)
            except httpx.HTTPStatusError as e:
                print(Fore.RED + f"[consumer] HTTP error from mirror node: {e}", file=sys.stderr)
                time.sleep(POLL_INTERVAL_SEC)
            except Exception as e:
                print(Fore.RED + f"[consumer] Unexpected error: {e}", file=sys.stderr)
                time.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":
    main()

