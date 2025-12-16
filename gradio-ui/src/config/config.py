from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    AGENT_RUNTIME_URL: str =  "http://agent-runtime:8000"
