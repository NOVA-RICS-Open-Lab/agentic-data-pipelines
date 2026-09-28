from mcp.server.fastmcp import FastMCP
import sys
import os
import logging
from mcp.server.transport_security import TransportSecuritySettings
import os
import asyncio
import httpx
from typing import Any
from urllib.parse import quote

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

grafana_mcp = FastMCP(
    "grafana_server",
    instructions="""
        MCP server for Grafana management. Exposes async tools to check Grafana health, list datasources, delete a datasource by name, and create an Infinity plugin datasource. Connection is made via basic auth using environment variables. Tools:
        - grafana_check_status: confirm Grafana is reachable and report version/database status.
        - list_datasources: return full datasource list for duplicate detection.
        - delete_datasource: remove a datasource by name.
        - create_infinity_datasource: create a yesoreyeram-infinity-datasource pointing at a REST endpoint (verbatim provided).

        The server uses an httpx.AsyncClient cached across calls. All network calls raise httpx.HTTPStatusError on 4xx/5xx; tools handle and translate those into JSON-friendly statuses. Environment variables configure URL, credentials, timeout and TLS verification.
    """,
)

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://grafana:3000")
GRAFANA_USER = os.getenv("GRAFANA_USER")
GRAFANA_PASSWORD = os.getenv("GRAFANA_PASSWORD")
GRAFANA_TIMEOUT = int(os.getenv("GRAFANA_TIMEOUT", "10"))
_CLIENT: httpx.AsyncClient | None = None

def _get_client() -> httpx.AsyncClient:
    """
    Return a cached AsyncClient configured with basic auth when credentials are present.
    This avoids constructing a client on every tool call.
    """
    global _CLIENT
    if _CLIENT is None:
        auth = None
        if GRAFANA_USER is not None or GRAFANA_PASSWORD is not None:
            # httpx accepts a tuple for Basic Auth
            auth = (GRAFANA_USER, GRAFANA_PASSWORD)
        # create client with reasonable limits; rely on environment-provided TLS flag
        _CLIENT = httpx.AsyncClient(auth=auth)
    return _CLIENT

async def _request(method: str, path: str, json: dict | None = None) -> Any:
    """
    Perform an HTTP request against the Grafana server and return parsed JSON or text.
    Raises httpx.HTTPStatusError for non-2xx responses so callers can inspect status_code.
    """
    client = _get_client()
    # ensure single slash semantics
    url = GRAFANA_URL.rstrip('/') + path
    try:
        resp = await client.request(method, url, json=json, timeout=GRAFANA_TIMEOUT)
        resp.raise_for_status()
        if resp.status_code == 204:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text
    except Exception:
        # let callers handle exceptions (including HTTPStatusError)
        raise

async def _get(path: str) -> Any:
    """Convenience wrapper for GET requests."""
    return await _request("GET", path)

async def _post(path: str, payload: dict) -> Any:
    """Convenience wrapper for POST requests."""
    return await _request("POST", path, json=payload)

async def _delete(path: str) -> Any:
    """Convenience wrapper for DELETE requests.

    Special-case: if deleting by name using the legacy '/api/datasources/name/<name>' path
    we URL-encode the name portion to avoid accidental URL issues.
    """
    # if the caller passed the legacy delete-by-name path, encode the trailing segment
    prefix = "/api/datasources/name/"
    if path.startswith(prefix):
        name_part = path[len(prefix):]
        encoded = quote(name_part, safe='')
        path = prefix + encoded
    return await _request("DELETE", path)

@grafana_mcp.tool()
async def grafana_check_status() -> dict:
    """
    Confirms that Grafana is reachable and usable before any datasource work begins.
    Calls GET /api/health through _get and reports the Grafana URL, its version and the state of its internal database.
    Must be called before create_infinity_datasource.
    """
    try:
        response = await _get("/api/health")
        return {
            "status": "ok",
            "grafana_url": GRAFANA_URL,
            "version": response.get("version"),
            "database_status": response.get("database"),  
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@grafana_mcp.tool()
async def list_datasources() -> dict:
    """
    Reports the datasources configured in Grafana, each with its id, name, type and url.
    Used to confirm that no datasource with the intended name or URL exists before creation.
    """
    try:
        datasources = await _get("/api/datasources")
        return {"status": "ok", "datasources": datasources}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@grafana_mcp.tool()
async def delete_datasource(name: str) -> dict:
    """
    Removes a datasource by its name through DELETE /api/datasources/name/<name>.
    Only the Grafana connection is removed: the data in MongoDB and the grafana-bridge service are untouched.
    A 404 means no datasource of that name exists, returned as not found.
    """
    try:
        await _delete(f"/api/datasources/name/{name}")
        return {"status": "deleted", "name": name}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"status": "not_found", "name": name}
        return {"status": "error", "detail": str(e)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@grafana_mcp.tool()
async def create_infinity_datasource(name: str, url: str) -> dict:
    """
    Create an Infinity datasource in Grafana pointing to a REST API endpoint.
    Always call list_datasources first to avoid creating duplicates.
    Always call grafana_check_status before calling this.
    The yesoreyeram-infinity-datasource plugin must be installed in the Grafana container.

    The agent should derive the URL from the pipeline AAS submodels:
    - Read Utilization submodel to get database and collection
    - Construct URL as http://grafana-bridge:8090/api/<database>/<collection>

    name: datasource display name   e.g. 'Kuka Readings'
    url:  REST API endpoint         e.g. 'http://grafana-bridge:8090/api/kuka/kuka_readings'
    """
    try:
        payload = {
            "name": name,
            "type": "yesoreyeram-infinity-datasource",
            "access": "proxy",
            "url": url,
            "basicAuth": False,
            "isDefault": False,
            "jsonData": {
                "tlsSkipVerify": True
            }
        }
        result = await _post("/api/datasources", payload)
        return {
            "status": "created",
            "id": result.get("id"),
            "name": name,
            "url": url
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return {"status": "already_exists", "name": name}
        return {"status": "error", "detail": str(e)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


if __name__ == "__main__":
    mode = os.getenv("MCP_CONNECTION_MODE", "stdio").lower()
    logger.info(f"Starting Grafana MCP server in {mode} mode")

    if mode == "http":
        PORT_VAR = "GRAFANA_MCP_PORT"
        port = int(os.getenv("PORT") or os.getenv(PORT_VAR) or 8110)
        logger.info(f"HTTP mode - listening on port {port} (set PORT or {PORT_VAR} to override)")
        grafana_mcp.settings.port = port
        grafana_mcp.settings.host = "0.0.0.0"
        grafana_mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        grafana_mcp.run(transport="streamable-http")
    else:
        logger.info("STDIO mode")
        grafana_mcp.run(transport="stdio")