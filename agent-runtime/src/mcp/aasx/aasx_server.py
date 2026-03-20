from mcp.server.fastmcp import FastMCP
from src.mcp.aasx import AASClient # type: ignore
import sys
import os
import logging
import random
import subprocess
import sys
from src.config.config import Config
from mcp.server.transport_security import TransportSecuritySettings

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

aasx_mcp = FastMCP("aasx_server",
                   instructions="""
                        This server exposes tools to interact with an AAS (Asset Administration Shell) server
                        following the AAS V3 / BaSyx API specification.

                        Available tool groups:
                        - READ:   describe_system, describe_one_shell, get_submodel, get_submodel_standalone,
                                get_submodels_refs, get_submodel_element, get_submodel_element_value
                        - WRITE:  create_shell, create_submodel, update_shell, update_submodel_element,
                                update_submodel_element_value, add_submodel_element
                        - LINK/DELETE-Link:   link_submodel, delete_submodel_ref_to_shell
                        - DELETE: delete_shell, delete_submodel, delete_submodel_element
                        - UTIL:   generate_aas_numeric_id, save_aas_changes

                        All IDs are full IRIs. Use generate_aas_numeric_id() to produce valid ones.
                        PATCH returns 204 on success. DELETE returns 204 on success.
                        """
                        )

def enrich_shell(shell: dict) -> dict:
    shell_id = shell["id"]
    shell["submodels_content"] = []
    for sm_ref in shell.get("submodels", []):
        try:
            sm_id = sm_ref["keys"][0]["value"]
            try:
                shell["submodels_content"].append(AASClient.get_submodel(shell_id, sm_id))
            except Exception:
                shell["submodels_content"].append(AASClient.get_submodel_standalone(sm_id))
        except (KeyError, IndexError):
            continue
    return shell

def enrich_one_shell_submodels(shell_id: str) -> dict:
    shell = AASClient.get_shell(shell_id)
    shell["submodels_content"] = []
    for sm_ref in shell.get("submodels", []):
        try:
            sm_id = sm_ref["keys"][0]["value"]
            try:
                shell["submodels_content"].append(AASClient.get_submodel(shell_id, sm_id))
            except Exception:
                shell["submodels_content"].append(AASClient.get_submodel_standalone(sm_id))
        except (KeyError, IndexError):
            continue
    return shell


@aasx_mcp.tool()
async def describe_system() -> list[dict]:
    """Lists all shells by name and ID only. Use describe_one_shell to get full details."""
    return AASClient.list_shells()


##To Make future changes in the AAS

@aasx_mcp.tool()
async def describe_one_shell(shell_id: str) -> dict:
    """
    Fetch a shell and all its submodel contents by shell ID.
    IMPORTANT: shell_id must be the FULL IRI, e.g. 'https://example.com/ids/aas/9092_3161_2062_8148'.
    Never pass idShort or partial IDs.
    """
    return enrich_one_shell_submodels(shell_id)


@aasx_mcp.tool()
async def get_submodel(shell_id: str, submodel_id: str) -> dict:
    """
    Get all submodel references from a shell.
    IMPORTANT: shell_id must be the FULL IRI, e.g. 'https://example.com/ids/aas/9092_3161_2062_8148'.
    Never pass idShort or partial IDs.
    """
    return AASClient.get_submodel(shell_id, submodel_id)


@aasx_mcp.tool()
async def add_submodel_element(shell_id: str, id_short_path: str, element: dict) -> dict:
    return AASClient.add_submodel_element(shell_id, id_short_path, element)

@aasx_mcp.tool()
async def update_submodel_element_value(shell_id: str, submodel_id: str, id_short_path: str, element: dict) -> dict:
    return AASClient.update_submodel_element_value(shell_id, submodel_id, id_short_path, element)

@aasx_mcp.tool()
async def create_submodel(submodel: dict) -> dict:
    """Create a new submodel. Pass the complete submodel dictionary."""
    return AASClient.create_submodel(submodel)

@aasx_mcp.tool()
async def get_submodels_refs(shell_id: str) ->dict:
    """Get all submodel references from one shell"""
    return AASClient.get_submodels_refs(shell_id)

@aasx_mcp.tool()
async def get_submodel_standalone(submodel_id: str) -> dict:
    """Fetch a submodel directly by its ID without needing a shell context."""
    return AASClient.get_submodel_standalone(submodel_id)

@aasx_mcp.tool()
async def link_submodel(shell_id: str, submodel_id: str) -> dict:
    """Link an existing submodel to a shell."""
    submodel_reference = {
        "type": "ModelReference",           
        "keys": [                            
            {
                "type": "Submodel",          
                "value": submodel_id         
            }
        ]
    }
    return AASClient.link_submodel_to_shell(shell_id, submodel_reference)

@aasx_mcp.tool()
async def generate_aas_numeric_id(is_submodel: bool) -> str:
    """Generates a unique-style numeric ID following the 4-group pattern: XXXX_XXXX_XXXX_XXXX
     is_submodel=True  → https://example.com/ids/sm/XXXX_XXXX_XXXX_XXXX
    is_submodel=False → https://example.com/ids/aas/XXXX_XXXX_XXXX_XXXX
    """
    parts = ["".join(random.choices("0123456789", k=4)) for _ in range(4)]
    numeric_id = "_".join(parts)
    if(is_submodel):
        return f"https://example.com/ids/sm/{numeric_id}"
    else: return f"https://example.com/ids/aas/{numeric_id}"

@aasx_mcp.tool()
async def create_shell(shell_payload: dict) -> dict:
    """
    Creates a new AAS Shell on the server.

    shell_payload must be a flat JSON dict — never wrapped in an outer key.
    Required fields:
    - id: full IRI from generate_aas_numeric_id(is_submodel=False)
    - idShort: string name
    - modelType: "AssetAdministrationShell"
    - assetInformation: {
        "assetKind": "Instance",
        "globalAssetId": <same value as id if the user did not specify one>
      }

    Do NOT include 'submodels_content' — that is a local enrichment field only.
    Do NOT wrap the payload: pass the dict directly, not as {"payload": {...}}.
    """
    return AASClient.create_shell(shell_payload)

@aasx_mcp.tool()
async def update_shell(shell_id: str, shell_payload: dict) -> dict:
    """Update an existing shell by its full IRI."""
    return AASClient.update_shell(shell_id, shell_payload)

@aasx_mcp.tool()
async def delete_shell(shell_id: str) -> dict:
    """Delete a shell by its full IRI."""
    return AASClient.delete_shell(shell_id)

@aasx_mcp.tool()
async def get_submodel_element(submodel_id: str) -> dict:
    """Get all elements of a submodel by its full IRI."""
    return AASClient.get_submodel_element(submodel_id)

@aasx_mcp.tool()
async def get_submodel_element_value(submodel_id: str, id_short_path: str) -> dict:
    """Get the raw $value of a specific submodel element."""
    return AASClient.get_submodel_element_value(submodel_id, id_short_path)

@aasx_mcp.tool()
async def update_submodel_element(submodel_id: str, id_short_path: str, element: dict) -> dict:
    """Full PUT replacement of a submodel element."""
    return AASClient.update_submodel_element(submodel_id, id_short_path, element)

@aasx_mcp.tool()
async def delete_submodel(submodel_id: str) -> dict:
    """Delete a standalone submodel by its full IRI."""
    return AASClient.delete_submodel(submodel_id)

@aasx_mcp.tool()
async def delete_submodel_element(submodel_id: str, id_short_path: str) -> dict:
    """Delete a submodel element by its idShort path."""
    return AASClient.delete_submodel_element(submodel_id, id_short_path)

@aasx_mcp.tool()
async def delete_submodel_ref_to_shell(shell_id: str, submodel_id: str) -> dict:
    """Unlink a submodel from a shell without deleting the submodel itself."""
    return AASClient.delete_submodel_ref_to_shell(shell_id, submodel_id)


@aasx_mcp.tool()
async def save_aas_changes(shell_id: str) -> str:
    """
    Persists a newly created shell to the local aasxs/ folder as a valid .aasx file
    so it survives server restarts. Only saves shells that don't already have a file
    on disk — existing .aasx files are never modified.
    
    Always call this after create_shell, passing the full shell IRI.
    """
    try:
        cmd = [
            sys.executable, "-m", "src.mcp.aasx.save_aasx",
            "--shell-id", shell_id,
            "--url", Config.AAS_BASE_URL,
            "--out", Config.AASX_AGENT_DIR,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            return f"Save failed:\n{result.stderr}"

        return f"Save successful:\n{result.stdout}"

    except Exception as e:
        return f"Save error: {e}"

if __name__ == "__main__":  
    mode = os.getenv("MCP_CONNECTION_MODE", "stdio").lower()
    logger.info(f"Starting AASX MCP server in {mode} mode")
    
    if mode == "http":
        port = int(os.getenv("PORT", 8080))
        logger.info(f"HTTP mode - listening on port {port}")

        aasx_mcp.settings.port = port
        aasx_mcp.settings.host = "0.0.0.0"
        aasx_mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)


        aasx_mcp.run(transport="streamable-http")
    else:
        logger.info("STDIO mode")
        aasx_mcp.run(transport="stdio")
