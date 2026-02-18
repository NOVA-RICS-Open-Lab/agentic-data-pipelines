from mcp.server.fastmcp import FastMCP
from src.mcp.aasx import AASClient # type: ignore
import sys
import os
import logging
import random

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

                        CLONING RULE:
                        When creating submodels based on a template, ALWAYS replace the 'id' field 
                        with a freshly generated ID from generate_aas_numeric_id(is_submodel=True).
                        Never POST a submodel using an ID that already exists on the server — 
                        this causes a 409 Conflict. Generate the ID first, then inject it into 
                        the submodel JSON before calling create_submodel.
                        Remove the 'semanticId' filed entirely from the root level before posting
                        — BaSyx may reject with 409 if semanticId conflicts with an existing submodel
                        
                        JSON VALIDATION:
                        BaSyx V3 requires 'id' and 'idShort' at the root. 
                        Do not wrap 'id' inside an 'identification' object.
                        Always include 'modelType': 'Submodel' and 'kind': 'Instance'.
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
async def describe_system() -> dict:
    return [enrich_shell(shell) for shell in AASClient.list_shells()] # type: ignore


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
