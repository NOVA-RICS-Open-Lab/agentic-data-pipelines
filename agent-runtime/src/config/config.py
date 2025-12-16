from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    AAS_BASE_URL: str = "http://aasx-server:5001"
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password123"
