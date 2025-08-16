# app.py
import os
import sys
import uuid
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from x402.fastapi.middleware import require_payment  # x402 FastAPI middleware

# --- Hedera SDK imports ---
from hedera import Client, TopicId, TopicMessageSubmitTransaction, AccountId, PrivateKey

# ------------- Colored logging -------------
from colorama import init as colorama_init, Fore, Style

colorama_init(autoreset=True)

class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Style.DIM + Fore.BLUE,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Style.BRIGHT + Fore.RED,
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, "")
        message = super().format(record)
        return f"{color}{message}{Style.RESET_ALL}"

def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("beatbank")
    logger.setLevel(logging.INFO)
    # Avoid duplicate handlers on uvicorn reload
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(ColorFormatter("[%(asctime)s] %(levelname)s:%(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
    return logger

logger = _setup_logger()

# ------------------------------------------
load_dotenv()

# ---------------- Env ----------------
PAY_TO_ADDRESS = os.getenv("PAY_TO_ADDRESS")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# Hedera config
HEDERA_NETWORK = os.getenv("HEDERA_NETWORK", "testnet").lower()
HEDERA_OPERATOR_ID = os.getenv("HEDERA_OPERATOR_ID")
HEDERA_OPERATOR_KEY = os.getenv("HEDERA_OPERATOR_KEY")
HEDERA_TOPIC_ID = os.getenv("HEDERA_TOPIC_ID")

if not PAY_TO_ADDRESS:
    raise RuntimeError("PAY_TO_ADDRESS is not set. See .env.example")

if not (HEDERA_OPERATOR_ID and HEDERA_OPERATOR_KEY and HEDERA_TOPIC_ID):
    raise RuntimeError("Set HEDERA_OPERATOR_ID, HEDERA_OPERATOR_KEY, HEDERA_TOPIC_ID in your .env")

# ---------------- Hedera compatibility helpers (snake_case vs camelCase) ----------------
def _client_for(network: str) -> Client:
    if network == "testnet":
        ctor = getattr(Client, "for_testnet", None) or getattr(Client, "forTestnet", None)
    elif network == "previewnet":
        ctor = getattr(Client, "for_previewnet", None) or getattr(Client, "forPreviewnet", None)
    else:
        ctor = getattr(Client, "for_mainnet", None) or getattr(Client, "forMainnet", None)
    if not ctor:
        raise RuntimeError("Hedera Client factory not found (for_testnet/forTestnet, etc.).")
    return ctor()

def _from_string(cls, s: str):
    fn = getattr(cls, "fromString", None) or getattr(cls, "from_string", None)
    if fn:
        return fn(s)
    return cls(s)

def _set_operator(client: Client, account_id: AccountId, private_key: PrivateKey):
    setter = getattr(client, "set_operator", None) or getattr(client, "setOperator", None)
    if not setter:
        raise RuntimeError("Client.set_operator/setOperator not found.")
    return setter(account_id, private_key)

def _topic_from_string(s: str) -> TopicId:
    fn = getattr(TopicId, "fromString", None) or getattr(TopicId, "from_string", None)
    return fn(s) if fn else TopicId(s)

def _as_str(x) -> str:
    """Stringify Hedera Java/Python objects nicely."""
    to_string = getattr(x, "toString", None)
    return to_string() if callable(to_string) else str(x)

# Mirror node base URL by network
MIRROR_BASE = {
    "testnet":   "https://testnet.mirrornode.hedera.com",
    "previewnet":"https://previewnet.mirrornode.hedera.com",
    "mainnet":   "https://mainnet-public.mirrornode.hedera.com",
}.get(HEDERA_NETWORK, "https://testnet.mirrornode.hedera.com")

# ---------------- Hedera client ----------------
def _hedera_client() -> Client:
    c = _client_for(HEDERA_NETWORK)
    op_id = _from_string(AccountId, HEDERA_OPERATOR_ID)
    op_key = _from_string(PrivateKey, HEDERA_OPERATOR_KEY)
    _set_operator(c, op_id, op_key)
    return c

HEDERA = _hedera_client()
TOPIC_ID = _topic_from_string(HEDERA_TOPIC_ID)

# ---------------- FastAPI ----------------
app = FastAPI(title="BeatBank x402 Uploader", version="0.1.3")

# Gate the /upload route behind x402 payments for $0.001
app.middleware("http")(
    require_payment(
        price="$0.001",
        pay_to_address=PAY_TO_ADDRESS,
        path="/upload",
        description="BeatBank: pay-per-upload MP3 to AI-separated stems (Hedera workflow; Walrus storage).",
        mime_type="application/json",
        output_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "BeatBankUploadResponse",
            "type": "object",
            "required": ["ok", "job_id", "filename"],
            "properties": {
                "ok": {"type": "boolean"},
                "job_id": {"type": "string"},
                "filename": {"type": "string"},
                "saved_to": {"type": "string"},
                "note": {"type": "string"},
                "hedera_topic_id": {"type": "string"},
                "hedera_message_id": {"type": "string"},
                "hedera_sequence": {"type": "integer"},
                "hedera_mirror_url": {"type": "string", "format": "uri"},
                "status_url": {"type": "string", "format": "uri"},
                "walrus_ref": {"type": "string"},
                "payment": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": True,
        },
    )
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ---------------- Hedera publish ----------------
def publish_hcs_received(job_id: str, filename: str) -> tuple[str, int]:
    """
    Publish a compact 'received' event to Hedera.
    Returns (transaction_id_str, topic_sequence_number).
    """
    payload = {"event": "received", "job_id": job_id, "filename": filename}
    msg_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    tx = TopicMessageSubmitTransaction().setTopicId(TOPIC_ID).setMessage(msg_bytes)
    resp = tx.execute(HEDERA)
    receipt = resp.getReceipt(HEDERA)
    seq = int(getattr(receipt, "topicSequenceNumber", 0))

    tx_id_str = _as_str(resp.transactionId)
    topic_str = _as_str(TOPIC_ID)

    # High‑visibility colored line for Hedera publish
    logger.info(
        "%sHedera HCS publish OK%s | topic=%s seq=%s tx=%s\n   payload=%s\n   mirror=%s",
        Fore.CYAN + Style.BRIGHT,
        Style.RESET_ALL,
        topic_str,
        seq,
        tx_id_str,
        payload,
        f"{MIRROR_BASE}/api/v1/topics/{topic_str}/messages/{seq}",
    )
    return tx_id_str, seq

# ---------------- Routes ----------------
@app.get("/")
def root():
    return {"ok": True, "service": "BeatBank x402 Uploader", "hedera_topic_id": _as_str(TOPIC_ID)}

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    job_id = str(uuid.uuid4())
    out_path = UPLOAD_DIR / f"{job_id}__{file.filename}"

    # Save to disk
    contents = await file.read()
    out_path.write_bytes(contents)

    # Publish 'received' event to Hedera
    try:
        hedera_tx_id, hedera_seq = publish_hcs_received(job_id, file.filename)
    except Exception as e:
        logger.exception("Hedera publish failed")
        raise HTTPException(status_code=500, detail=f"Hedera publish failed: {e}")

    topic_str = _as_str(TOPIC_ID)
    mirror_msg_url = f"{MIRROR_BASE}/api/v1/topics/{topic_str}/messages/{hedera_seq}"
    status_url = f"http://{HOST}:{PORT}/jobs/{job_id}"  # placeholder for future status endpoint

    return JSONResponse(
        {
            "ok": True,
            "job_id": job_id,
            "filename": file.filename,
            "saved_to": str(out_path),
            "note": "Payment received via x402. File accepted; processing pipeline TBD.",
            "hedera_topic_id": topic_str,
            "hedera_message_id": hedera_tx_id,   # tx id
            "hedera_sequence": hedera_seq,       # sequence #
            "hedera_mirror_url": mirror_msg_url, # direct link to verify
            "status_url": status_url,
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)

