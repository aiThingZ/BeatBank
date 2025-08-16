# client_payer.py
import os
import asyncio
from dotenv import load_dotenv
from eth_account import Account
import httpx

from x402.clients.httpx import x402_payment_hooks  # adds x402 auto-pay behavior

load_dotenv()

# WARNING: for demo only; keep keys safe in real usage
PRIVATE_KEY = os.getenv("PRIVATE_KEY") or "0xYOUR_TEST_PRIVATE_KEY"
SERVER = os.getenv("SERVER", "http://127.0.0.1:8000")
TEST_FILE = os.getenv("TEST_FILE", "demo.mp3")

async def main():
    acct = Account.from_key(PRIVATE_KEY)

    async with httpx.AsyncClient(base_url=SERVER, timeout=60.0) as client:
        # Install x402 hooks so 402 flows auto-pay
        client.event_hooks = x402_payment_hooks(acct)

        files = {"file": (os.path.basename(TEST_FILE), open(TEST_FILE, "rb"), "audio/mpeg")}
        resp = await client.post("/upload", files=files)
        print(resp.status_code, resp.json())

if __name__ == "__main__":
    asyncio.run(main())

