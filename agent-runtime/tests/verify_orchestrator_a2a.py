import sys
import os
from fastapi import FastAPI

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agents.orchestrator import OrchestratorAgent

def test_get_a2a_app():
    agent = OrchestratorAgent()
    app = agent.get_a2a_app()
    assert isinstance(app, FastAPI), f"Expected FastAPI instance, got {type(app)}"
    print("Verification successful: get_a2a_app() returns a FastAPI instance.")

if __name__ == "__main__":
    test_get_a2a_app()
