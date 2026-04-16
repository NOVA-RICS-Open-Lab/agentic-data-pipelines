import asyncio
import json
import os
from confluent_kafka import Producer
from asyncua import Client, Node, ua
from uuid import uuid4

topic = os.getenv("topic", "opcua.kuka.raw")
producer = Producer({"bootstrap.servers": os.getenv("bootstrap_server", "broker:9092")})

class SubscriptionHandler:
    def datachange_notification(self, node: Node, val, data):
        unique_id = str(uuid4())
        message = json.dumps({
            "source_type": "opcua",
            "asset_id": str(node.nodeid),
            "timestamp": data.monitored_item.Value.SourceTimestamp.isoformat() if data.monitored_item.Value.SourceTimestamp else None,
            "quality": "good",
            "value": val,
            "unit": None
        })
        print(f"Data change: {node.nodeid} -> {val}", flush=True)
        producer.produce(topic, value=message.encode(), key=unique_id.encode())
        producer.flush()

async def get_all_variables(client: Client, nsidx: int, folder_name: str) -> list:
    root_folder = await client.nodes.objects.get_child(f"{nsidx}:{folder_name}")
    return await browse_variables(root_folder)

async def browse_variables(node: Node) -> list:
    variables = []
    children = await node.get_children()
    for child in children:
        class_id = await child.read_node_class()
        if class_id == ua.NodeClass.Variable:
            variables.append(child)
        elif class_id == ua.NodeClass.Object:
            variables.extend(await browse_variables(child))
    return variables

async def main():
    url = os.getenv("url", "opc.tcp://kuka-robot:4849")
    namespace = os.getenv("namespace", "http://fct.unl.pt/kuka_robot/")
    folder = os.getenv("folder", "Kuka_Robot")

    async with Client(url) as client:
        nsidx = await client.get_namespace_index(namespace)
        
        opcua_nodes = await get_all_variables(client, nsidx, folder)
        print(f"Discovered {len(opcua_nodes)} variables:")
        for n in opcua_nodes:
            browse_name = await n.read_browse_name()
            node_id = n.nodeid
            val = await n.read_value()
            print(f"  - {browse_name} | NodeId: {node_id} | Value: {val}", flush=True)

        handler = SubscriptionHandler()
        subscription = await client.create_subscription(500, handler)
        await subscription.subscribe_data_change(opcua_nodes)

        while True:
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())