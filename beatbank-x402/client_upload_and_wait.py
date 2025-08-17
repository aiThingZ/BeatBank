#!/usr/bin/env python3
# client_payer.py
import os
import asyncio
import time
import json
import base64
from typing import Optional

from dotenv import load_dotenv
from eth_account import Account
import httpx

from x402.clients.httpx import x402_payment_hooks  # adds x402 auto-pay behavior

load_dotenv()

# ---- Env ----
PRIVATE_KEY = os.getenv("PRIVATE_KEY")  # EVM key for x402 payments (unchanged)
SERVER = os.getenv("SERVER", "http://127.0.0.1:8000")
TEST_FILE = os.getenv("TEST_FILE", "demo.mp3")
POLL_INTERVAL_SEC = float(os.getenv("POLL_INTERVAL_SEC", "2"))
POLL_TIMEOUT_SEC = float(os.getenv("POLL_TIMEOUT_SEC", "180"))

# Validate private key (same behavior as before)
if not PRIVATE_KEY:
    print("❌ Error: PRIVATE_KEY is not set in the environment or .env file.")
    raise SystemExit(1)

def _decode_msg(b64: str):
    """Decode a base64 mirror-node message into JSON (or text)."""
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return {"error": "base64_decode_failed"}
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"text": raw.decode("utf-8", errors="replace")}

async def _poll_for_ready(mirror_base: str, topic_id: str, job_id: str, seq_start: int) -> Optional[dict]:
    """
    Poll the Hedera mirror node for a 'ready' event for this job_id with sequence > seq_start.
    Returns the decoded message dict or None on timeout.
    """
    url = f"{mirror_base}/api/v1/topics/{topic_id}/messages?order=desc&limit=50"
    deadline = time.time() + POLL_TIMEOUT_SEC

    async with httpx.AsyncClient(timeout=30.0) as client:
        while time.time() < deadline:
            try:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
                for m in data.get("messages", []):
                    seq = int(m.get("sequence_number", 0))
                    if seq <= seq_start:
                        continue
                    decoded = _decode_msg(m.get("message", ""))
                    # Expect server to publish: {"event":"ready","job_id":"...","walrus_ref":"..."}
                    if isinstance(decoded, dict) and decoded.get("event") == "ready" and decoded.get("job_id") == job_id:
                        print(f"✅ Found READY on Hedera (seq={seq}): {decoded}")
                        return decoded
                await asyncio.sleep(POLL_INTERVAL_SEC)
            except Exception as e:
                print(f"[poll] mirror error: {e}")
                await asyncio.sleep(POLL_INTERVAL_SEC)

    print(f"⏳ Timeout waiting for 'ready' (job_id={job_id}) after {int(POLL_TIMEOUT_SEC)}s")
    return None

async def main():
    acct = Account.from_key(PRIVATE_KEY)
    print(f"🔑 Payer address: {acct.address}")
    print(f"🌐 Server: {SERVER}")
    print(f"🎵 Uploading: {TEST_FILE}")

    if not os.path.exists(TEST_FILE):
        print(f"❌ File not found: {TEST_FILE}")
        raise SystemExit(2)

    files = {"file": (os.path.basename(TEST_FILE), open(TEST_FILE, "rb"), "audio/mpeg")}

    async with httpx.AsyncClient(base_url=SERVER, timeout=60.0) as client:
        # keep original x402 behavior
        client.event_hooks = x402_payment_hooks(acct)

        # 1) Upload (x402 handles 402->pay->retry internally)
        resp = await client.post("/upload", files=files)
        try:
            info = resp.json()
        except Exception:
            info = {"raw": await resp.aread()}
        print(f"HTTP {resp.status_code} {info}")

        if resp.status_code != 200:
            raise SystemExit(3)

    # 2) Extract Hedera polling hints from server response
    try:
        topic_id = info["hedera_topic_id"]
        seq_start = int(info["hedera_sequence_start"])
        mirror_base = info["hedera_mirror_base"]
        job_id = info["job_id"]
    except KeyError as e:
        print(f"❌ Server response missing {e}. Got keys: {list(info.keys())}")
        print("   The server should return hedera_topic_id, hedera_sequence_start, hedera_mirror_base, job_id.")
        raise SystemExit(4)

    print(f"🛰️ Polling Hedera mirror for READY (topic={topic_id}, after seq={seq_start}, job_id={job_id}) …")
    ready = await _poll_for_ready(mirror_base, topic_id, job_id, seq_start)

    if ready:
        walrus_ref = ready.get("walrus_ref")
        print(f"🎉 Stems ready! walrus_ref={walrus_ref}")
        raise SystemExit(0)
    else:
        raise SystemExit(5)

if __name__ == "__main__":
    asyncio.run(main())

