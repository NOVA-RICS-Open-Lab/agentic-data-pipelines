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
                    ID GENERATION RULE:
                    All new submodel IDs MUST follow this exact pattern:
                    https://example.com/ids/sm/XXXX_XXXX_XXXX_XXXX   (submodel)
                    https://example.com/ids/aas/XXXX_XXXX_XXXX_XXXX  (shell)
                    where each X is a random digit. Always call generate_aas_numeric_id() to produce IDs. Never invent IDs manually.

                    ─────────────────────────────────────────────
                    SUBMODEL CREATION — MANDATORY SEQUENCE
                    ─────────────────────────────────────────────
                    Follow these steps IN ORDER. Never skip or reorder them.

                    STEP 1 — Generate ID first:
                    Call generate_aas_numeric_id(is_submodel=True).
                    Store the returned value. This is the ONLY valid ID for the new submodel.

                    STEP 2 — Fetch a reference submodel:
                    Call get_submodel_standalone() on an existing submodel from the server.
                    Use its structure as the base. Never construct a submodel schema from memory.

                    STEP 3 — Build the payload:
                    - Set "id" to the value returned in STEP 1. No other value is acceptable.
                    - Set "idShort" to the new submodel name.
                    - Replace element values as needed.
                    - Remove "semanticId" from the ROOT LEVEL ONLY. Nested semanticIds inside
                        submodelElements must be kept exactly as they are.
                    - Never copy the "id" from the reference submodel. That ID already exists
                        and will cause a 409 Conflict.
                    - Never add elements that do not exist in the reference submodel. If new
                        elements are needed, copy the closest matching element from the reference
                        and modify it. Never invent element structures from memory.

                    STEP 4 — Validate the payload structure:
                    The payload MUST match this structure exactly before calling create_submodel:

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

                    VALIDATION CHECKLIST — every item must pass before proceeding:
                    ✓ "id" is present at root level (not inside "identification" or any wrapper)
                    ✓ "idShort" is present at root level
                    ✓ "modelType" is "Submodel"
                    ✓ "kind" is "Instance"
                    ✓ No "semanticId" at root level
                    ✓ No AAS V2 fields: "idType", "identification"
                    ✓ Payload is NOT wrapped in any outer key (e.g. no {"submodel": {...}})
                    ✓ All valueType values use xs: prefix — "xs:string", "xs:int", "xs:boolean",
                        "xs:float", "xs:date", "xs:anyURI" — never plain "string" or "integer"
                    ✓ All xs:date values use ISO 8601 format with dashes: "YYYY-MM-DD"
                    ✓ All xs:dateTime values use ISO 8601 format: "YYYY-MM-DDTHH:MM:SS"
                    ✓ No valueType mismatch — if valueType is "xs:integer" the value must be
                        a number, not a string. If the value is text, use "xs:string" instead.
                    ✓ Every File element has a "contentType" field (see FILE ELEMENT RULE below)

                    STEP 5 — Call create_submodel:
                    Pass the validated payload. Do NOT call link_submodel before this succeeds.

                    STEP 6 — Handle 409 Conflict autonomously (do NOT ask the user):
                    On first 409:
                        → Remove "semanticId" from root level if still present, retry with same ID.
                    On second 409:
                        → Call generate_aas_numeric_id(is_submodel=True) for a brand new ID.
                        → Rebuild the payload with the new ID, retry.
                    On third 409:
                        → Call generate_aas_numeric_id(is_submodel=True) for another brand new ID.
                        → Rebuild the payload with the new ID, retry.
                    If all three attempts fail:
                        → Report the error to the user, listing all three IDs that were attempted.
                    Never stop to ask the user during this retry loop.

                    STEP 7 — Handle 400 Bad Request autonomously (do NOT ask the user):
                    A 400 means the payload has a schema or validation error. Do the following:
                    1. Re-run the full VALIDATION CHECKLIST from STEP 4 against the payload.
                    2. Fix every item that fails the checklist.
                    3. Pay special attention to: date formats, valueType mismatches, File elements.
                    4. Retry create_submodel with the corrected payload.
                    5. If a second 400 occurs, report the error and the full payload to the user.
                    Never stop to ask the user on the first 400 — always attempt self-correction.

                    STEP 8 — Link the submodel:
                    Only call link_submodel AFTER create_submodel returns a success response.
                    A 409 from link_submodel is acceptable — it means the submodel is already
                    linked. Treat it as success and continue.

                    STEP 9 — Save:
                    Always call save_aas_changes() as the final step after any create, update,
                    or delete operation. Never finish a task that modifies the AAS without saving.

                    ─────────────────────────────────────────────
                    FILE ELEMENT RULE
                    ─────────────────────────────────────────────
                    Every element with "modelType": "File" MUST include a "contentType" field.

                    Valid example:
                    {
                        "idShort": "ReleaseInfo",
                        "modelType": "File",
                        "contentType": "text/plain",
                        "value": "/aasx/files/releasenotes.txt"
                    }

                    If a File element from the reference submodel has no value or no contentType,
                    OMIT it entirely from the cloned payload. Never copy an incomplete File element.
                    Incomplete File elements will cause a 400 Bad Request.

                    ─────────────────────────────────────────────
                    VALUE TYPE RULE
                    ─────────────────────────────────────────────
                    The "valueType" and "value" fields must always be compatible:
                    xs:string    → value is any text string
                    xs:int       → value is a whole number, e.g. 42
                    xs:float     → value is a decimal number, e.g. 3.14
                    xs:boolean   → value is "true" or "false"
                    xs:date      → value is "YYYY-MM-DD"
                    xs:dateTime  → value is "YYYY-MM-DDTHH:MM:SS"
                    xs:anyURI    → value is a valid URI string

                    If the actual value does not match the declared valueType, change the
                    valueType to match the value — never change the value to fit a wrong type.

                    ─────────────────────────────────────────────
                    DELETE RESPONSE RULE
                    ─────────────────────────────────────────────
                    A DELETE returning HTTP 204 with no response body is a SUCCESS.
                    Do not treat an empty body on DELETE as an error. Continue normally.

                    ─────────────────────────────────────────────
                    SAVING RULE
                    ─────────────────────────────────────────────
                    Always call save_aas_changes(shell_id=<the shell's full IRI>) after any create,
                    update, or delete. Only omit shell_id if explicitly saving all shells.
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
