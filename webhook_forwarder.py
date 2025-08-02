import os
import json
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, Request, HTTPException
import httpx
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

FORWARD_URL = os.getenv("FORWARD_URL")

if not FORWARD_URL:
    raise EnvironmentError("FORWARD_URL not set in environment variables or .env file")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),  # Log to stdout
        logging.FileHandler("webhook_forwarder.log")  # Log to a log file
    ]
)

app = FastAPI()

LOG_FILE = "webhook_log.jsonl"

@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        # Parse incoming JSON payload
        payload: Dict[str, Any] = await request.json()
        timestamp = datetime.utcnow().isoformat()

        # Log payload with timestamp to file (JSON Lines format)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            entry = {"timestamp": timestamp, "payload": payload}
            f.write(json.dumps(entry) + "\n")

        logging.info("Received and logged webhook payload")

        # Forward the JSON payload as-is to FORWARD_URL
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(FORWARD_URL, json=payload)

            if response.status_code >= 400:
                logging.error(f"Forwarding failed: {response.status_code} - {response.text}")
                # Still return 200 to sender; webhook endpoints should not leak internal errors
            else:
                logging.info(f"Successfully forwarded payload to {FORWARD_URL}")

        return {"ok": True}

    except httpx.RequestError as e:
        logging.error(f"HTTP error during forwarding: {str(e)}")
        return {"ok": True}  # Don't raise to caller; log and continue

    except Exception as e:
        logging.exception(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")