"""Operator console: a single FastAPI app fronting multiple chat-capable agents.

Replaces the old per-agent Gradio Blocks apps. One static page with a sidebar
lets the operator pick which agent to talk to; each agent is constructed
eagerly (cheap) but only `initialize()`d (expensive: opens MCP connections)
the first time it is selected, tracked per-agent so a slow init on one agent
never blocks another.

Chat streams as NDJSON events ({"type": "token", "text": ...} etc.) rather
than raw text, so the System Agent can also surface deploy_candidate events
inline - see src/agents/system.py's run(). Deploy actions themselves are
proxied to docker-mcp-service, the one container with docker-socket access.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Protocol

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
DOCKER_MCP_BASE_URL = os.getenv("DOCKER_MCP_BASE_URL", "http://docker-mcp-service:8087")


class StreamingAgent(Protocol):
    initialized: bool

    async def initialize(self) -> None: ...
    def run(self, prompt: str) -> AsyncIterator: ...


@dataclass
class AgentSlot:
    key: str
    label: str
    agent: StreamingAgent
    status: str = "idle"  # idle | initializing | ready | error
    error: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ChatRequest(BaseModel):
    message: str


class DeployRequest(BaseModel):
    file_path: str
    port: int


def create_console_app(agents: list[tuple[str, str, StreamingAgent]], title: str = "Operator Console") -> FastAPI:
    """Build the console app. `agents` is a list of (key, label, agent instance)."""

    slots: dict[str, AgentSlot] = {
        key: AgentSlot(key=key, label=label, agent=agent) for key, label, agent in agents
    }

    app = FastAPI(title=title)

    index_html = (
        (STATIC_DIR / "index.html")
        .read_text(encoding="utf-8")
        .replace("{{TITLE}}", title)
    )

    def get_slot(key: str) -> AgentSlot:
        slot = slots.get(key)
        if slot is None:
            raise HTTPException(status_code=404, detail=f"unknown agent '{key}'")
        return slot

    async def do_initialize(slot: AgentSlot) -> None:
        async with slot.lock:
            if slot.status == "ready":
                return
            slot.status = "initializing"
            slot.error = None
            try:
                logger.info(f"Initializing agent '{slot.key}'...")
                await slot.agent.initialize()
                slot.status = "ready"
                logger.info(f"Agent '{slot.key}' ready")
            except Exception as exc:
                logger.exception(f"Failed to initialize agent '{slot.key}'")
                slot.status = "error"
                slot.error = str(exc)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return index_html

    @app.get("/api/agents")
    async def list_agents():
        return [
            {"key": s.key, "label": s.label, "status": s.status, "error": s.error}
            for s in slots.values()
        ]

    @app.post("/api/agents/{key}/init")
    async def init_agent(key: str):
        slot = get_slot(key)
        if slot.status in ("ready", "initializing"):
            return {"status": slot.status}
        asyncio.create_task(do_initialize(slot))
        return {"status": "initializing"}

    @app.get("/api/agents/{key}/status")
    async def agent_status(key: str):
        slot = get_slot(key)
        return {"status": slot.status, "error": slot.error}

    @app.post("/api/agents/{key}/chat")
    async def chat(key: str, req: ChatRequest):
        slot = get_slot(key)
        if slot.status != "ready":
            raise HTTPException(
                status_code=409, detail=f"agent '{key}' not ready (status: {slot.status})"
            )

        async def event_stream() -> AsyncIterator[str]:
            # The HTTP response has already been committed (200) by the time the
            # first token is yielded, so an exception raised inside agent.run()
            # cannot become an error status - it would just cut the stream and
            # the UI would hang forever. Turn it into a final "error" event so
            # the client can show what went wrong.
            try:
                async for item in slot.agent.run(req.message):
                    event = item if isinstance(item, dict) else {"type": "token", "text": item}
                    yield json.dumps(event) + "\n"
            except asyncio.CancelledError:
                raise  # client disconnected - not an error to report
            except Exception as exc:
                logger.exception(f"chat stream for agent '{key}' failed")
                yield json.dumps({"type": "error", "message": f"{type(exc).__name__}: {exc}"}) + "\n"

        return StreamingResponse(event_stream(), media_type="application/x-ndjson")

    @app.get("/api/deploy/suggest-port")
    async def suggest_port():
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DOCKER_MCP_BASE_URL}/deploy/suggest-port", timeout=10)
            resp.raise_for_status()
            return resp.json()

    @app.post("/api/deploy")
    async def deploy(req: DeployRequest):
        async def proxy_stream() -> AsyncIterator[bytes]:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{DOCKER_MCP_BASE_URL}/deploy",
                    json=req.model_dump(),
                    timeout=600,
                ) as resp:
                    async for chunk in resp.aiter_bytes():
                        yield chunk

        return StreamingResponse(proxy_stream(), media_type="application/x-ndjson")

    return app
