from mcp.server.fastmcp import FastMCP

# Initialize server with name
mcp = FastMCP("Generic Server 1")

# Example generic tool
@mcp.tool()
async def echo(message: str) -> str:
    """Echo back the message."""
    return f"Echo: {message}"

@mcp.tool()
async def add_numbers(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b

# Run as STDIO server (local subprocess)
def main():
    # This is STDIO mode, suitable for local subprocess
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
