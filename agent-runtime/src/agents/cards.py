from typing import List, Dict

ORCHESTRATOR_CARD = {
    "@context": "https://google.github.io/a2a/context.jsonld",
    "type": "Agent",
    "name": "OrchestratorAgent",
    "description": "Coordinates research and generation tasks to build data pipelines tools.",
    "capabilities": ["execute_task"]
}

RESEARCHER_CARD = {
    "@context": "https://google.github.io/a2a/context.jsonld",
    "type": "Agent",
    "name": "ResearcherAgent",
    "description": "Performs web searches and extracts data about specific softwares to be used/deployed in building data pipelines tools.",
    "capabilities": ["search", "analyze"]
}

GENERATOR_CARD = {
    "@context": "https://google.github.io/a2a/context.jsonld",
    "type": "Agent",
    "name": "GeneratorAgent",
    "description": "Generates MCP Tools to be used for data pipelines deployment.",
    "capabilities": ["generate_pipeline", "create_aasx"]
}

REVIEWER_CARD = {
    "@context": "https://google.github.io/a2a/context.jsonld",
    "type": "Agent",
    "name": "ReviewerAgent",
    "description": "Reviews code that is going to be deployed for pipeline components.",
    "capabilities": []
}
