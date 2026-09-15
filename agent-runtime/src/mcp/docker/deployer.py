import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import AsyncIterator

logger = logging.getLogger(__name__)

REPO_ROOT = Path(os.getenv("REPO_ROOT", "/workspace")).resolve()
COMPOSE_FILE = Path(os.getenv("COMPOSE_FILE", str(REPO_ROOT / "docker-compose.yml")))
PROJECT_NAME = os.getenv("COMPOSE_PROJECT_NAME", "agentic-data-pipelines")

GENERATED_DIR = (REPO_ROOT / "agent-runtime" / "generated").resolve()
MCP_SRC_DIR = (REPO_ROOT / "agent-runtime" / "src" / "mcp").resolve()

AUTO_DEPLOY_MARKER = "# ===== AUTO-DEPLOYED MCP SERVERS ====="
MARKER_ANCHOR = "AUTO-DEPLOYED MCP SERVERS"
PORT_RE = re.compile(r'^\s*-\s*"?(\d+):\d+"?\s*$', re.MULTILINE)
TECH_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class DeployError(RuntimeError):
    """Raised when a deploy request can't be safely carried out."""


def _detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _used_ports() -> set[int]:
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    return {int(m.group(1)) for m in PORT_RE.finditer(text)}


def suggest_port(start: int = 9100) -> int:
    used = _used_ports()
    port = start
    while port in used:
        port += 1
    return port


def _validate_generated_path(file_path: str) -> Path:
    """file_path comes from an HTTP request body, not directly from the agent -
    it round-tripped through the browser, so it's untrusted input here even
    though the Generator/Reviewer already vetted the code itself."""
    try:
        path = Path(file_path)
        if not path.is_absolute():
            path = (REPO_ROOT / "agent-runtime" / path).resolve()
        else:
            path = path.resolve()
    except (OSError, ValueError) as e:
        raise DeployError(f"Invalid file path: {e}") from e

    try:
        path.relative_to(GENERATED_DIR)
    except ValueError:
        raise DeployError(f"'{file_path}' is not under generated/") from None

    if not path.is_file():
        raise DeployError(f"'{path}' does not exist")

    return path


def _append_compose_service(technology: str, service_name: str, port: int) -> None:
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    nl = _detect_newline(text)

    block_lines = [
        f"  {service_name}:",
        "    build: ./agent-runtime",
        f"    container_name: {service_name}",
        f"    command: python -m src.mcp.{technology}.{technology}_server",
        "    ports:",
        f'      - "{port}:{port}"',
        "    env_file:",
        "      - .env",
        "    environment:",
        "      - MCP_CONNECTION_MODE=http",
        f"      - PORT={port}",
        "    networks:",
        "      - agentic-net",
        "",
    ]
    block = nl.join(block_lines)

    networks_match = re.search(r"^networks:\s*$", text, re.MULTILINE)
    if not networks_match:
        raise DeployError("Could not find a top-level 'networks:' key in docker-compose.yml")

    insert_at = networks_match.start()

    if MARKER_ANCHOR in text:
        # Marker already exists further up (from a previous deploy) - insert right after
        # whatever line contains it, however it's currently worded/indented.
        marker_pos = text.index(MARKER_ANCHOR)
        line_end = text.index("\n", marker_pos) + 1
        new_text = text[:line_end] + block + nl + text[line_end:]
    else:
        banner = nl.join([AUTO_DEPLOY_MARKER, "", block, ""])
        new_text = text[:insert_at] + banner + text[insert_at:]

    COMPOSE_FILE.write_text(new_text, encoding="utf-8")


async def deploy(file_path: str, port: int) -> AsyncIterator[str]:
    """Copy the generated server into src/mcp/, wire it into compose, build+start it.

    Yields human-readable log lines as it goes.
    """
    src = _validate_generated_path(file_path)
    technology = src.parent.name

    if not TECH_RE.match(technology):
        raise DeployError(f"Unexpected technology name derived from path: '{technology}'")
    if src.name != f"{technology}_server.py":
        raise DeployError(f"Unexpected file name '{src.name}' for technology '{technology}'")

    if not (1024 <= port <= 65535):
        raise DeployError(f"Port {port} is out of range")
    if port in _used_ports():
        raise DeployError(f"Port {port} is already used by another service")

    service_name = f"{technology}-mcp-service"
    yield f"Deploying '{technology}' as '{service_name}' on port {port}..."

    dest_dir = MCP_SRC_DIR / technology
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    yield f"Copied {src.name} -> agent-runtime/src/mcp/{technology}/{src.name}"

    _append_compose_service(technology, service_name, port)
    yield f"Added '{service_name}' to docker-compose.yml"

    yield "Building image and starting the container (this can take a minute)..."
    proc = await asyncio.create_subprocess_exec(
        "docker", "compose", "-f", str(COMPOSE_FILE), "-p", PROJECT_NAME,
        "up", "-d", "--build", service_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    assert proc.stdout is not None
    async for raw_line in proc.stdout:
        yield raw_line.decode(errors="replace").rstrip()

    returncode = await proc.wait()
    if returncode != 0:
        raise DeployError(f"docker compose exited with code {returncode}")

    yield f"'{service_name}' is up on port {port}."
