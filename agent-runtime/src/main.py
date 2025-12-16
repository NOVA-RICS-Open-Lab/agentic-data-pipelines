from fastapi import FastAPI
from  src.config import Settings

app = FastAPI(title="Agentic Pipelines")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/config")
def config():
    settings = Settings()
    return {
        "aas_url": settings.AAS_BASE_URL,
        "neo4j_uri": settings.NEO4J_URI,
    }
