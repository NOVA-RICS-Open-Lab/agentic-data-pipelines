from src.config import Settings
import httpx
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
        Settings.NEO4J_URI, auth=(Settings.NEO4J_USER, Settings.NEO4J_PASSWORD)
    )

class Tools:

    def list_aas_shells():
        url = f"{Settings.AAS_BASE_URL}/shells"
        with httpx.Client(timeout=5) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.json()

    def run_cypher(query, params=None):
        with driver.session() as session:
            return list(session.run(query, params or {}))