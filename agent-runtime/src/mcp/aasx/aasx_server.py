from mcp.server.fastmcp import FastMCP
from src.mcp.aasx import AASClient

aasx_mcp = FastMCP("aasx_server")

def enrich_shell(shell: dict) -> dict:
    shell_id = shell["id"]
    shell["submodels_content"] = []
    for sm_ref in shell.get("submodels", []):
        try:
            sm_id = sm_ref["keys"][0]["value"]
            shell["submodels_content"].append(AASClient.get_submodel(shell_id, sm_id))
        except (KeyError, IndexError):
            continue
    return shell


@aasx_mcp.tool()
async def describe_system() -> dict:
    return [enrich_shell(shell) for shell in AASClient.list_shells()]


if __name__ == "__main__":
    aasx_mcp.run(transport="stdio")
