import os
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

grafana_mcp = FastMCP("grafana-mcp")

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://grafana:3000")
GRAFANA_USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
GRAFANA_PASSWORD = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _auth() -> tuple:
    return (GRAFANA_USER, GRAFANA_PASSWORD)


async def _get(path: str) -> dict:
    async with httpx.AsyncClient() as http:
        resp = await http.get(
            f"{GRAFANA_URL}{path}",
            auth=_auth(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()


async def _post(path: str, payload: dict) -> dict:
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{GRAFANA_URL}{path}",
            json=payload,
            auth=_auth(),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()


async def _delete(path: str) -> dict:
    async with httpx.AsyncClient() as http:
        resp = await http.delete(
            f"{GRAFANA_URL}{path}",
            auth=_auth(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()


# ── Tools ─────────────────────────────────────────────────────────────────────

@grafana_mcp.tool()
async def grafana_check_status() -> dict:
    """
    Check if Grafana is reachable.
    Always call this first before creating datasources or dashboards.
    """
    try:
        result = await _get("/api/health")
        return {
            "reachable": True,
            "url": GRAFANA_URL,
            "version": result.get("version", "unknown"),
            "database": result.get("database", "unknown")
        }
    except Exception as e:
        return {
            "reachable": False,
            "url": GRAFANA_URL,
            "error": str(e)
        }


@grafana_mcp.tool()
async def list_datasources() -> dict:
    """
    List all configured Grafana datasources.
    Use this to verify a datasource exists before creating a duplicate.
    """
    try:
        datasources = await _get("/api/datasources")
        return {
            "count": len(datasources),
            "datasources": [
                {
                    "id": ds.get("id"),
                    "name": ds.get("name"),
                    "type": ds.get("type"),
                    "url": ds.get("url"),
                    "database": ds.get("database")
                }
                for ds in datasources
            ]
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@grafana_mcp.tool()
async def create_infinity_datasource(
    name: str,
    url: str,
) -> dict:
    """
    Create an Infinity datasource in Grafana pointing to a REST API endpoint.
    Always call list_datasources first to avoid creating duplicates.
    Always call grafana_check_status before calling this.
    The yesoreyeram-infinity-datasource plugin must be installed in the Grafana container.
 
    The agent should derive the URL from the pipeline AAS submodels:
    - Read Utilization submodel to get database and collection
    - Construct URL as http://kuka-api-service:8090/api/<database>/<collection>
 
    name: datasource display name   e.g. 'Kuka Readings'
    url:  REST API endpoint         e.g. 'http://kuka-api-service:8090/api/kuka/kuka_readings'
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


@grafana_mcp.tool()
async def delete_datasource(name: str) -> dict:
    """
    Delete a Grafana datasource by name.
    The data in MongoDB is preserved — only the Grafana connection is removed.

    name: datasource display name to delete   e.g. 'Kuka MongoDB'
    """
    try:
        result = await _delete(f"/api/datasources/name/{name}")
        return {"status": "deleted", "name": name, "message": result.get("message")}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"status": "not_found", "name": name}
        return {"status": "error", "detail": str(e)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8089))
    grafana_mcp.settings.port = port
    grafana_mcp.settings.host = "0.0.0.0"
    grafana_mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    grafana_mcp.run(transport="streamable-http")