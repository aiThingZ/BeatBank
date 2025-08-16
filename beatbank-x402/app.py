# app.py
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from x402.fastapi.middleware import require_payment  # x402 FastAPI middleware

load_dotenv()

PAY_TO_ADDRESS = os.getenv("PAY_TO_ADDRESS")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

if not PAY_TO_ADDRESS:
    raise RuntimeError("PAY_TO_ADDRESS is not set. See .env.example")

app = FastAPI(title="BeatBank x402 Uploader", version="0.1.0")

# Gate the /upload route behind x402 payments for $0.001
# (minimum supported by x402; '.001 cents' would be $0.00001 which is below min)
app.middleware("http")(
    require_payment(
        price="$0.001",
        pay_to_address=PAY_TO_ADDRESS,
        path="/upload",
    )
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@app.get("/")
def root():
    return {"ok": True, "service": "BeatBank x402 Uploader"}

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    # Basic sanity check
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    job_id = str(uuid.uuid4())
    out_path = UPLOAD_DIR / f"{job_id}__{file.filename}"

    # Save to disk (streaming for large files would be better later)
    contents = await file.read()
    out_path.write_bytes(contents)

    # TODO (next steps you’ll add):
    # - enqueue Demucs stem job
    # - publish "received" message on Hedera
    # - when done, upload to Walrus and publish "ready" message on Hedera

    return JSONResponse(
        {
            "ok": True,
            "job_id": job_id,
            "filename": file.filename,
            "saved_to": str(out_path),
            "note": "Payment received via x402. File accepted; processing pipeline TBD.",
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)

