import os
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.errors import PyMongoError

MONGO_URI = os.getenv("MONGO_URI") or f"mongodb://{os.getenv('MONGO_USERNAME')}:{os.getenv('MONGO_PASSWORD')}@mongodb:27017"
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)

NAME = r"^[A-Za-z0-9_-]{1,63}$"

app = FastAPI()


class Reading(BaseModel):
    source_type: str
    asset_id: str
    timestamp: Optional[str] = None
    quality: Optional[str] = None
    value: Any = None
    unit: Optional[str] = None


@app.post("/ingest/{database}/{collection}", status_code=202)
def ingest(
    readings: List[Reading],
    database: str = Path(pattern=NAME),
    collection: str = Path(pattern=NAME),
):
    if not readings:
        return {"inserted": 0}
    received_at = datetime.now(timezone.utc).isoformat()
    docs = [{**r.model_dump(), "received_at": received_at} for r in readings]
    try:
        result = client[database][collection].insert_many(docs, ordered=False)
    except PyMongoError as e:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {e}")
    return {"inserted": len(result.inserted_ids)}


@app.get("/health")
def health():
    try:
        client.admin.command("ping")
    except PyMongoError as e:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {e}")
    return {"status": "ok"}