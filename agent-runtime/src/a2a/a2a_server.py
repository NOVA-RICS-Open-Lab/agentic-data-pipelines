import uvicorn
import os
import asyncio
import logging
from src.agents import OrchestratorAgent, ResearcherAgent, GeneratorAgent, ReviewerAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    agent_type = os.getenv("AGENT_TYPE", "orchestrator").lower()
    port = int(os.getenv("PORT", 8000))
    
    if agent_type == "orchestrator":
        agent = OrchestratorAgent()
    elif agent_type == "researcher":
        agent = ResearcherAgent()
    elif agent_type == "generator":
        agent = GeneratorAgent()
    elif agent_type == "reviewer":
        agent = ReviewerAgent()
    else:
        raise ValueError(f"Unknown AGENT_TYPE: {agent_type}")
    
    logger.info(f"Initializing {agent_type} agent...")
    await agent.initialize()
    
    app = agent.get_a2a_app()
    
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
