import os
import httpx
from asyncua import Client, ua
from asyncua.common.node import Node
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

opcua_mcp = FastMCP("opcua-mcp")


@opcua_mcp.tool()
async def browse_nodes(endpoint: str, node_id: str = "ns=0;i=85") -> list:
    """
    Recursively browse all nodes from a starting point.
    endpoint: OPC UA server endpoint
    node_id:  starting node (defaults to Objects folder - browses everything)
    """
    async with Client(endpoint) as client:
        start_node = client.get_node(node_id)
        nodes = []
        await _collect_nodes(start_node, nodes, depth=0, max_depth=5)
        return nodes


@opcua_mcp.tool()
async def read_node(endpoint: str, node_id: str) -> dict:
    """
    Read the value of a single node by its node_id.
    endpoint: OPC UA server endpoint
    node_id:  e.g. 'ns=1;s=Power_kW'
    """
    async with Client(endpoint) as client:
        node = client.get_node(node_id)
        value = await node.get_value()
        name = await node.read_browse_name()
        return {"node_id": node_id, "name": str(name), "value": value}


@opcua_mcp.tool()
async def read_nodes(endpoint: str, node_ids: list[str]) -> list:
    """
    Read multiple nodes in a single connection.
    endpoint: OPC UA server endpoint
    node_ids: list of node id strings
    """
    async with Client(endpoint) as client:
        results = []
        for node_id in node_ids:
            try:
                node = client.get_node(node_id)
                value = await node.get_value()
                name = await node.read_browse_name()
                results.append({"node_id": node_id, "name": str(name), "value": value, "error": None})
            except Exception as e:
                results.append({"node_id": node_id, "name": None, "value": None, "error": str(e)})
        return results


@opcua_mcp.tool()
async def read_all_values(endpoint: str, node_id: str = "ns=0;i=85") -> list:
    """
    Browse and read all variable values from a starting node in one call.
    endpoint: OPC UA server endpoint
    node_id:  starting node (defaults to Objects folder)
    """
    async with Client(endpoint) as client:
        start_node = client.get_node(node_id)
        snapshot = []
        await _collect_values(start_node, snapshot, depth=0, max_depth=5)
        return snapshot


async def _collect_nodes(node: Node, result: list, depth: int, max_depth: int):
    if depth > max_depth:
        return
    try:
        for child in await node.get_children():
            try:
                name = await child.read_browse_name()
                node_class = await child.read_node_class()
                result.append({"node_id": child.nodeid.to_string(), "name": str(name), "node_class": str(node_class), "depth": depth})
                await _collect_nodes(child, result, depth + 1, max_depth)
            except Exception:
                continue
    except Exception:
        pass


async def _collect_values(node: Node, result: list, depth: int, max_depth: int):
    if depth > max_depth:
        return
    try:
        for child in await node.get_children():
            try:
                node_class = await child.read_node_class()
                name = await child.read_browse_name()
                if node_class == ua.NodeClass.Variable:
                    value = await child.get_value()
                    result.append({"node_id": child.nodeid.to_string(), "name": str(name), "value": value})
                await _collect_values(child, result, depth + 1, max_depth)
            except Exception:
                continue
    except Exception:
        pass


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8082))
    opcua_mcp.settings.port = port
    opcua_mcp.settings.host = "0.0.0.0"
    opcua_mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    opcua_mcp.run(transport="streamable-http")