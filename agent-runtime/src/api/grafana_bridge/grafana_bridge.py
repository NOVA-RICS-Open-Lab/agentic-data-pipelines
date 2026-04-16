from fastapi import FastAPI
from pymongo import MongoClient
from bson import json_util
import os
import json

app = FastAPI()
MONGO_URI = os.getenv("MONGO_URI") or f"mongodb://{os.getenv('MONGO_USERNAME')}:{os.getenv('MONGO_PASSWORD')}@mongodb:27017"
client = MongoClient(MONGO_URI)

@app.get("/api/{database}/{collection}")
async def get_readings(database: str, collection: str, limit: int = 100):
    docs = client[database][collection].find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit)
    return json.loads(json_util.dumps(list(docs)))