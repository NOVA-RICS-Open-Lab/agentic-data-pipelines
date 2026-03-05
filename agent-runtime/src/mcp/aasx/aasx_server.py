from mcp.server.fastmcp import FastMCP
from src.mcp.aasx import AASClient # type: ignore
import sys
import os
import logging
import random
import subprocess
import sys

from mcp.server.transport_security import TransportSecuritySettings

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

aasx_mcp = FastMCP("aasx_server",
                   instructions="""
                        ID GENERATION RULE: 
                        All new submodel IDs must follow the pattern: https://example.com/ids/sm/XXXX_XXXX_XXXX_XXXX 
                        where X is a random digit. 

                        SUBMODEL CREATION RULE:
                        When creating a new submodel, ALWAYS first fetch an existing submodel from the server 
                        using get_submodel_standalone to use as a structural reference.
                        Copy the structure exactly, replace only id (generate a new one), idShort, and element values.
                        Never guess the schema from scratch.

                        SUBMODEL ID RULE:
                        The 'id' field is MANDATORY at the root of every submodel JSON before calling create_submodel.
                        Never call create_submodel without 'id' present at the root level.
                        A missing 'id' will cause a 409 or 400 error.

                        CLONING RULE:
                        When cloning a submodel from a template:
                        1. Call generate_aas_numeric_id(is_submodel=True) FIRST — before building any JSON
                        2. Store that returned ID
                        3. Use ONLY that returned ID in the 'id' field of the new submodel payload
                        4. NEVER copy the 'id' field from the template submodel — that ID already exists and will cause 409 Conflict
                        5. NEVER use an ID you did not receive from generate_aas_numeric_id in this session
                        6. Remove 'semanticId' from the root level before posting

                        409 AUTONOMOUS RECOVERY RULE:
                        If create_submodel returns 409:
                        1. Delete 'semanticId' from the root of the submodel JSON
                        2. Retry create_submodel immediately with the same ID
                        3. If it still returns 409, generate a brand new ID and retry once more
                        4. Never stop and ask the user what to do on a 409 — always recover autonomously

                        ORDER RULE:
                        Always create_submodel BEFORE link_submodel.
                        Never call link_submodel until create_submodel returns a successful response.
                        A 409 on link_submodel is acceptable (already linked). A 409 on create_submodel means stop and generate a new ID.

                        SAVING RULE:
                        After ANY operation that creates, updates, or deletes a shell or submodel,
                        ALWAYS call save_aas_changes() as the final step.
                        Never finish a task that modifies the AAS without saving.
                        
                        JSON VALIDATION:
                        BaSyx V3 requires 'id' and 'idShort' at the root. 
                        Do not wrap 'id' inside an 'identification' object.
                        Always include 'modelType': 'Submodel' and 'kind': 'Instance'.


                        SUBMODEL JSON STRUCTURE RULE:
                        A valid BaSyx V3 submodel MUST follow this exact structure. Never deviate from it:

                        {
                        "id": "https://example.com/ids/sm/XXXX_XXXX_XXXX_XXXX",
                        "idShort": "MySubmodel",
                        "modelType": "Submodel",
                        "kind": "Instance",
                        "submodelElements": [
                            {
                            "idShort": "MyProperty",
                            "modelType": "Property",
                            "valueType": "xs:string",
                            "value": "my_value"
                            }
                        ]
                        }

                        RULES:
                        - valueType MUST be "xs:string", "xs:int", "xs:boolean", "xs:float" — never plain "string" or "integer"
                        - Never wrap the payload in any outer key like "submodel": {...}
                        - Never include "idType", "identification", or any AAS V2 fields
                        - Never include "semanticId" at the root level
                        - submodelElements is a flat list — each element needs idShort, modelType, valueType, value
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
    shell_payload must be a complete AAS shell JSON with:
    - id: FULL IRI (e.g. 'https://example.com/ids/aas/XXXX_XXXX_XXXX_XXXX')
    - idShort: string name
    - modelType: 'AssetAdministrationShell'
    - assetInformation: dict with assetKind and globalAssetId
    Do NOT include 'submodels_content' - that is a local enrichment field only.
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
async def save_aas_changes() -> str:
    """
    Saves the current state of all AAS shells to the persistent aasxs_agent/ folder.
    Call this after creating, updating, or deleting any shell or submodel.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "src.mcp.aasx.save_aasx_changes"],
            capture_output=True,
            text=True,
            timeout=60
        )
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
