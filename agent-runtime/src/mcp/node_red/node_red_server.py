import os
import uuid
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

nodered_mcp = FastMCP("nodered-mcp")


SUPPORTED_SOURCES = ["opcua", "mqtt", "modbus", "http", "tcp"]
SUPPORTED_TARGETS = ["http", "mqtt", "tcp", "modbus", "kafka"]


#source node builders

def _source_opcua(node_id: str, endpoint: str, interval_ms: int, paths: list, target_id: str) -> list:
    nodes = []
    endpoint_config_id = f"endpoint-{node_id}"
    
    # 1. Endpoint Configuration
    nodes.append({
        "id": endpoint_config_id,
        "type": "OpcUa-Endpoint",
        "endpoint": endpoint,
        "secpol": "None", "secmode": "None", "none": True,
        "name": "Kuka Server Config"
    })

    repeat_seconds = str(int(interval_ms / 1000))

    # 2. Dynamic Inject Nodes
    for i, item in enumerate(paths):
        # Extract values provided by the Agent's AAS lookup
        path = item.get("path")
        dtype = item.get("datatype", "String") # Default to String if missing

        if not path.startswith("ns="):
            path = f"ns=2;s={path}"
        
        # Clean name for the UI
        display_name = path.split("/")[-1].split("=")[-1]

        nodes.append({
            "id": f"inject-{i}-{node_id}",
            "type": "inject",
            "name": f"Read {display_name}",
            "once": False,
            "onceDelay": 5,
            "repeat": repeat_seconds, 
            "props": [
                {"p": "payload", "vt": "date"}, 
                # Concatenate dynamically based on Agent input
                {"p": "topic", "vt": "str", "v": f"{path};datatype={dtype}"}
            ],
            "x": 100, "y": 100 + (i * 80),
            "wires": [[node_id]]
        })

    # 3. Client node (Action: Read)
    nodes.append({
        "id": node_id,
        "type": "OpcUa-Client",
        "name": "Kuka Collector",
        "endpoint": endpoint_config_id,
        "action": "read",
        "x": 400, "y": 150,
       "wires": [[target_id]]
    })
    return nodes

# def _source_opcua(node_id: str, endpoint: str, interval_ms: int, paths: list) -> list:
#     nodes = []
#     endpoint_config_id = f"endpoint-{node_id}"
    
#     # 1. Endpoint Config remains the same
#     nodes.append({
#         "id": endpoint_config_id,
#         "type": "OpcUa-Endpoint",
#         "endpoint": endpoint,
#         "secpol": "None", "secmode": "None", "none": True,
#         "name": "Kuka OPC-UA Endpoint"
#     })

#     # 2. Direct Inject Nodes (One per sensor)
#     for i, path in enumerate(paths):
#         # Determine datatype hint based on the path name
#         dtype = "Double" if "Power_W" in path else "Boolean" if "Is_Closed" in path else "String"
        
#         nodes.append({
#             "id": f"inject-{i}-{node_id}",
#             "type": "inject",
#             "once": True,
#             "onceDelay": 5,
#             "repeat": "2", # Re-fires every 2 seconds (Polling)
#             "props": [
#                 # Format exactly like the tutorial: ns=2;s=Path;datatype=Type
#                 {"p": "topic", "vt": "str", "v": f"{path};datatype={dtype}"},
#                 {"p": "payload", "vt": "str", "v": "read"} # Tells client to 'read'
#             ],
#             "x": 100, "y": 100 + (i * 80),
#             "wires": [[node_id]] # Wire DIRECTLY to Client, bypassing Item nodes
#         })

#     # 3. Client node (Action: Read)
#     nodes.append({
#         "id": node_id,
#         "type": "OpcUa-Client",
#         "name": "Kuka Collector",
#         "endpoint": endpoint_config_id,
#         "action": "read", # Changed from 'subscribe' to 'read'
#         "x": 400, "y": 150,
#         "wires": [[]]
#     })
#     return nodes

# def _source_opcua(node_id: str, endpoint: str, interval_ms: int, paths: list) -> list:
#     nodes = []
    
#     endpoint_config_id = f"endpoint-{node_id}"
    
#     # 1. Setup the Endpoint Configuration
#     nodes.append({
#         "id": endpoint_config_id,
#         "type": "OpcUa-Endpoint",
#         "endpoint": endpoint,
#         "secpol": "None",
#         "secmode": "None",
#         "none": True,
#         "login": False,
#         "usercert": False,
#         "name": "Kuka OPC-UA Endpoint"
#     })

#     # 2. Create an Inject and Item node for EACH path
#     for i, path in enumerate(paths):
#         # The Inject node acts as the "Start" button for the subscription
#         nodes.append({
#             "id": f"inject-{i}-{node_id}",
#             "type": "inject",
#             "once": True,
#             "onceDelay": 5,  # Wait 5s for the server to be ready
#             "repeat": "",    # Empty string means "Fire once and stop"
#             "props": [
#                 {"p": "topic", "vt": "str", "v": path} # This fixes the 'replace' error
#             ],
#             "x": 100, "y": 100 + (i * 60),
#             "wires": [[f"item-{i}-{node_id}"]]
#         })

#         # The Item node prepares the specific variable for the Client
#         nodes.append({
#             "id": f"item-{i}-{node_id}",
#             "type": "OpcUa-Item",
#             "item": path,
#             "name": path.split("/")[-1],
#             "x": 300, "y": 100 + (i * 60),
#             "wires": [[node_id]] # All items wire into the single Client node
#         })

#     # 3. The Client node (The actual worker)
#     nodes.append({
#         "id": node_id,
#         "type": "OpcUa-Client",
#         "name": "Kuka Collector",
#         "endpoint": endpoint_config_id,
#         "action": "subscribe",
#         "time": interval_ms,
#         "timeUnit": "ms",
#         "x": 500, "y": 150,
#         "wires": [[]] # This will be wired to your Kafka/Transform node later
#     })

#     return nodes


def _source_mqtt(node_id: str, endpoint: str, topic: str) -> list:
    host, port = endpoint.replace("mqtt://", "").split(":")
    broker_id = f"broker-{node_id}"
    return [
        {
            "id": broker_id,
            "type": "mqtt-broker",
            "name": "MQTT broker",
            "broker": host,
            "port": port,
        },
        {
            "id": node_id,
            "type": "mqtt in",
            "name": "MQTT source",
            "topic": topic,
            "broker": broker_id,
            "wires": []
        }
    ]


def _source_modbus(node_id: str, endpoint: str, interval_ms: int) -> list:
    host, port = endpoint.split(":")
    server_id = f"modbus-server-{node_id}"
    return [
        {
            "id": server_id,
            "type": "modbus-client",
            "name": "Modbus server",
            "clienttype": "tcp",
            "tcpHost": host,
            "tcpPort": port,
            "unit_id": 1,
        },
        {
            "id": node_id,
            "type": "modbus-read",
            "name": "Modbus source",
            "unitid": 1,
            "dataType": "HoldingRegister",
            "adr": 0,
            "quantity": 10,
            "rate": interval_ms,
            "rateUnit": "ms",
            "server": server_id,
            "wires": []
        }
    ]


def _source_http(node_id: str, path: str) -> list:
    return [{
        "id": node_id,
        "type": "http in",
        "name": "HTTP source",
        "url": path,
        "method": "post",
        "wires": []
    }]


def _source_tcp(node_id: str, endpoint: str) -> list:
    host, port = endpoint.split(":")
    return [{
        "id": node_id,
        "type": "tcp in",
        "name": "TCP source",
        "server": "client",
        "host": host,
        "port": port,
        "datamode": "stream",
        "datatype": "utf8",
        "wires": []
    }]




def _target_http(node_id: str, endpoint: str) -> list:
    return [{
        "id": node_id,
        "type": "http request",
        "name": "HTTP target",
        "method": "POST",
        "ret": "txt",
        "url": endpoint,
        "wires": []
    }]


def _target_mqtt(node_id: str, endpoint: str, topic: str) -> list:
    host, port = endpoint.replace("mqtt://", "").split(":")
    broker_id = f"broker-{node_id}"
    return [
        {
            "id": broker_id,
            "type": "mqtt-broker",
            "name": "MQTT broker",
            "broker": host,
            "port": port,
        },
        {
            "id": node_id,
            "type": "mqtt out",
            "name": "MQTT target",
            "topic": topic,
            "broker": broker_id,
            "wires": []
        }
    ]


def _target_tcp(node_id: str, endpoint: str) -> list:
    host, port = endpoint.split(":")
    return [{
        "id": node_id,
        "type": "tcp out",
        "name": "TCP target",
        "host": host,
        "port": port,
        "beserver": "client",
        "base64": False,
        "wires": []
    }]


def _target_modbus(node_id: str, endpoint: str) -> list:
    host, port = endpoint.split(":")
    server_id = f"modbus-server-{node_id}"
    return [
        {
            "id": server_id,
            "type": "modbus-client",
            "name": "Modbus server",
            "clienttype": "tcp",
            "tcpHost": host,
            "tcpPort": port,
            "unit_id": 1,
        },
        {
            "id": node_id,
            "type": "modbus-write",
            "name": "Modbus target",
            "unitid": 1,
            "dataType": "HoldingRegister",
            "adr": 0,
            "server": server_id,
            "wires": []
        }
    ]

def _target_kafka(node_id: str, endpoint: str, topic: str) -> list:
    # endpoint = "kafka:9092"
    broker_id = f"kafka-broker-{node_id}"
    return [
        {
            "id": broker_id,
            "type": "oriolrius-kafka-broker",   
            "name": "Kafka Broker",
            "hosts": endpoint,                  # "kafka:9092"
        },
        {
            "id": node_id,
            "type": "oriolrius-kafka-producer",
            "name": f"Kafka → {topic}",
            "topic": topic,
            "broker": broker_id,
            "wires": []
        }
    ]

def _transform_node(node_id: str, source_protocol: str, target_protocol: str) -> dict:
    
    if target_protocol == "kafka":
        func = (
            "msg.payload = JSON.stringify({\n"
            f"  source_type: '{source_protocol}',\n"
            "  asset_id: msg.topic || 'unknown',\n"
            "  timestamp: new Date().toISOString(),\n"
            "  data: msg.payload,\n"
            "  unit: msg.unit || null,\n"
            "  quality: msg.quality || 'good'\n"
            "});\n"
            "return msg;"
        )
    else:
        func = (
            "msg.payload = {\n"
            "  timestamp: new Date().toISOString(),\n"
            "  source: msg.topic || 'unknown',\n"
            "  readings: msg.payload\n"
            "};\n"
            "return msg;"
        )

    return {
        "id": node_id,
        "type": "function",
        "name": "Protocol_Transform",
        "func": func,
        "outputs": 1,
        "wires": []
    }



def _build_flow(
    bridge_id: str,
    source_protocol: str,
    source_endpoint: str,
    target_protocol: str,
    target_endpoint: str,
    topic: str,
    interval_ms: int,
    paths: list = []
) -> list:
    src_id = f"src-{bridge_id}"
    transf_id = f"transf-{bridge_id}"    ## Id of the transform 
    tgt_id = f"tgt-{bridge_id}"

    if source_protocol == "opcua":
        if not paths:
            raise ValueError("paths is required for opcua source protocol")
        src_nodes = _source_opcua(src_id, source_endpoint, interval_ms, paths, transf_id)
    elif source_protocol == "mqtt":
        src_nodes = _source_mqtt(src_id, source_endpoint, topic)
    elif source_protocol == "modbus":
        src_nodes = _source_modbus(src_id, source_endpoint, interval_ms)
    elif source_protocol == "http":
        src_nodes = _source_http(src_id, source_endpoint)
    elif source_protocol == "tcp":
        src_nodes = _source_tcp(src_id, source_endpoint)
    else:
        raise ValueError(f"Unsupported source protocol '{source_protocol}'. Supported: {SUPPORTED_SOURCES}")

    transf_node = _transform_node(transf_id, source_protocol, target_protocol)

    if target_protocol == "http":
        tgt_nodes = _target_http(tgt_id, target_endpoint)
    elif target_protocol == "mqtt":
        tgt_nodes = _target_mqtt(tgt_id, target_endpoint, topic)
    elif target_protocol == "tcp":
        tgt_nodes = _target_tcp(tgt_id, target_endpoint)
    elif target_protocol == "modbus":
        tgt_nodes = _target_modbus(tgt_id, target_endpoint)
    elif target_protocol == "kafka":
        if not topic:
            raise ValueError("topic is required for kafka target")
        tgt_nodes = _target_kafka(tgt_id, target_endpoint, topic)
    else:
        raise ValueError(f"Unsupported target protocol '{target_protocol}'. Supported: {SUPPORTED_TARGETS}")

    # wire: src → transf → tgt
    src_nodes[-1]["wires"] = [[transf_id]]
    transf_node["wires"] = [[tgt_id]]
    tgt_nodes[-1]["wires"] = [[]]

    tab = {
        "id": f"tab-{bridge_id}",
        "type": "tab",
        "label": f"{source_protocol} → {target_protocol}",
        "disabled": False,
        "info": f"bridge_id:{bridge_id}"
    }

    all_nodes = src_nodes + [transf_node] + tgt_nodes
    for node in all_nodes:
        node["z"] = f"tab-{bridge_id}"

    return [tab] + all_nodes




@nodered_mcp.tool()
async def deploy_bridge(
    nodered_endpoint: str,
    source_protocol: str,
    source_endpoint: str,
    target_protocol: str,
    target_endpoint: str,
    topic: str = "",
    interval_ms: int = 2000,
    paths: list = []
) -> dict:
    """
    Deploy a protocol bridge in Node-RED.

    nodered_endpoint: Node-RED admin API e.g. 'http://node-red:1880'
    source_protocol:  opcua | mqtt | modbus | http | tcp
    source_endpoint:  e.g. 'opc.tcp://kuka-robot:4849'
    target_protocol:  http | mqtt | tcp | modbus | kafka
    target_endpoint:  e.g. 'broker:9092' for kafka, 'http://host/path' for http
    topic:            required for mqtt and kafka targets. Use convention <protocol>.<asset> e.g. 'opcua.kuka.raw'
    interval_ms:      polling interval for opcua/modbus (default 2000ms)
    paths:            REQUIRED when source_protocol is 'opcua'.
                      List of OPC-UA node paths to subscribe to.
                      Derive these from the AAS Collection submodel parameters.
                      Format: "ns=<namespace>;s=<browse_path>"
                      Example:
                      [
                        "ns=2;s=Kuka_Robot/Energy_Measurement/Power_W;, datatype": "Double"",
                      ]

    Returns bridge_id — store this to delete the bridge later.
    """
    bridge_id = str(uuid.uuid4())[:8]

    flow = _build_flow(
        bridge_id=bridge_id,
        source_protocol=source_protocol,
        source_endpoint=source_endpoint,
        target_protocol=target_protocol,
        target_endpoint=target_endpoint,
        topic=topic,
        interval_ms=interval_ms,
        paths=paths,
    )

    async with httpx.AsyncClient() as http:
        # GET existing flows using v2 API
        resp = await http.get(
            f"{nodered_endpoint}/flows",
            headers={"Node-RED-API-Version": "v2"},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        existing_flows = data.get("flows", [])
        rev = data.get("rev")

        # POST updated flows using v2 API
        resp = await http.post(
            f"{nodered_endpoint}/flows",
            json={"flows": existing_flows + flow, "rev": rev},
            headers={
                "Content-Type": "application/json",
                "Node-RED-API-Version": "v2"
            },
            timeout=10
        )
        resp.raise_for_status()

    return {
        "bridge_id": bridge_id,
        "source_protocol": source_protocol,
        "source_endpoint": source_endpoint,
        "target_protocol": target_protocol,
        "target_endpoint": target_endpoint,
        "topic": topic,
        "interval_ms": interval_ms,
        "status": "deployed"
    }


@nodered_mcp.tool()
async def get_bridges(nodered_endpoint: str) -> list:
    """
    List all active bridges in Node-RED using v2 API.
    """
    async with httpx.AsyncClient() as http:
        resp = await http.get(
            f"{nodered_endpoint}/flows",
            headers={"Node-RED-API-Version": "v2"}, # Fixes version mismatch
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        # In v2, the flow list is nested inside the 'flows' key
        flows = data.get("flows", [])

    return [
        {
            "bridge_id": node.get("info", "").replace("bridge_id:", ""),
            "label": node.get("label", ""),
            "disabled": node.get("disabled", False)
        }
        for node in flows
        if node.get("type") == "tab"
        and node.get("info", "").startswith("bridge_id:")
    ]


@nodered_mcp.tool()
async def delete_bridge(nodered_endpoint: str, bridge_id: str) -> dict:
    """
    Remove a bridge from Node-RED by bridge_id.
    nodered_endpoint: e.g. 'http://node-red:1880'
    bridge_id: returned by deploy_bridge
    """
    async with httpx.AsyncClient() as http:
        resp = await http.get(
            f"{nodered_endpoint}/flows",
            headers={"Node-RED-API-Version": "v2"},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        flows = data.get("flows", [])
        rev = data.get("rev")

    tab_id = f"tab-{bridge_id}"
    updated = [
        n for n in flows
        if n.get("id") != tab_id and n.get("z") != tab_id
    ]

    if len(updated) == len(flows):
        return {"status": "not_found", "bridge_id": bridge_id}

    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{nodered_endpoint}/flows",
            json={"flows": updated, "rev": rev},
            headers={
                "Content-Type": "application/json",
                "Node-RED-API-Version": "v2"
            },
            timeout=10
        )
        resp.raise_for_status()

    return {"status": "deleted", "bridge_id": bridge_id}


@nodered_mcp.tool()
async def node_red_check_status(nodered_endpoint: str) -> dict:
    """
    Check if Node-RED is reachable.
    nodered_endpoint: e.g. 'http://node-red:1880'
    """
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(f"{nodered_endpoint}/settings", timeout=5)
            resp.raise_for_status()
            settings = resp.json()
        return {
            "reachable": True,
            "version": settings.get("version", "unknown"),
            "endpoint": nodered_endpoint
        }
    except Exception as e:
        return {"reachable": False, "error": str(e), "endpoint": nodered_endpoint}


@nodered_mcp.tool()
async def list_supported_protocols() -> dict:
    """
    Returns supported source and target protocols.
    Agent should call this to validate a protocol pair before deploying a bridge.
    """
    return {
        "source_protocols": SUPPORTED_SOURCES,
        "target_protocols": SUPPORTED_TARGETS,
    }




if __name__ == "__main__":
    port = int(os.getenv("PORT", 8086))
    nodered_mcp.settings.port = port
    nodered_mcp.settings.host = "0.0.0.0"
    nodered_mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    nodered_mcp.run(transport="streamable-http")