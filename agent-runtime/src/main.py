import logging
import sys

import uvicorn

from src.agents import GeneratorAgent, ResearcherAgent, SystemAgent
from src.ui.console_app import create_console_app

logging.basicConfig(level=logging.DEBUG, handlers=[
    logging.StreamHandler(sys.stderr)
])

app = create_console_app(
    [
        ("system", "System Agent", SystemAgent()),
        ("researcher", "Researcher", ResearcherAgent()),
        ("generator", "Generator", GeneratorAgent()),
    ],
    title="Agentic Pipelines Console",
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
