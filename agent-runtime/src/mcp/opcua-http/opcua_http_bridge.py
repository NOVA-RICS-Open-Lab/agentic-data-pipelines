import asyncio
import json
import os

import httpx
from asyncua import Client, Node, ua

TARGET_URL = os.getenv("target_url", "http://opcua-ingest:8098/ingest/kuka/opcua_raw")
BATCH_INTERVAL = 1.0   # seconds between successful POSTs
RETRY_DELAY = 2.0      # seconds before retrying a failed POST
MAX_BATCH = 500        # readings per POST
MAX_BUFFER = 10_000    # readings held while the receiver is unreachable

queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_BUFFER)


class SubscriptionHandler:
    def datachange_notification(self, node: Node, val, data):
        ts = data.monitored_item.Value.SourceTimestamp
        reading = {
            "source_type": "opcua",
            "asset_id": str(node.nodeid),
            "timestamp": ts.isoformat() if ts else None,
            "quality": "good",
            "value": val,
            "unit": None,
        }
        try:
            queue.put_nowait(reading)
        except asyncio.QueueFull:
            print(f"Buffer full, dropping: {node.nodeid}", flush=True)
            return
        print(f"Data change: {node.nodeid} -> {val}", flush=True)


async def sender(http: httpx.AsyncClient):
    batch: list = []
    while True:
        if not batch:
            batch.append(await queue.get())
        while len(batch) < MAX_BATCH and not queue.empty():
            batch.append(queue.get_nowait())
        try:
            resp = await http.post(
                TARGET_URL,
                content=json.dumps(batch, default=str),
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as e:
            print(f"POST failed ({e!r}), retrying batch of {len(batch)}", flush=True)
            await asyncio.sleep(RETRY_DELAY)
            continue
        if resp.status_code == 422:
            print(f"Receiver rejected batch of {len(batch)} (422): {resp.text[:200]}", flush=True)
            batch = []
        elif resp.status_code >= 400:
            print(f"Receiver returned {resp.status_code}, retrying batch of {len(batch)}", flush=True)
            await asyncio.sleep(RETRY_DELAY)
            continue
        else:
            print(f"Posted {len(batch)} readings", flush=True)
            batch = []
        await asyncio.sleep(BATCH_INTERVAL)


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
    print(f"Target: {TARGET_URL}", flush=True)

    async with httpx.AsyncClient(timeout=10) as http, Client(url) as client:
        sender_task = asyncio.create_task(sender(http))

        nsidx = await client.get_namespace_index(namespace)

        opcua_nodes = await get_all_variables(client, nsidx, folder)
        print(f"Discovered {len(opcua_nodes)} variables:", flush=True)
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
            if sender_task.done():
                sender_task.result()  # re-raise so the container restarts


if __name__ == "__main__":
    asyncio.run(main())