import asyncio
import logging
from asyncua import Server, ua
import random

async def main():
    # Setup server
    server = Server()
    await server.init()
    # Endpoint URI matches your AAS AssetInterfacesDescription
    server.set_endpoint("opc.tcp://0.0.0.0:4849")
    server.set_server_name("Kuka_Robot")

    # Setup namespace
    uri = "http://fct.unl.pt/kuka_robot/"
    idx = await server.register_namespace(uri)

    # Create Object Tree based on your Robot_Components
    objects = server.nodes.objects
    kuka = await objects.add_folder(idx, "Kuka_Robot")

    # Component: Robot_Controller (KR C4)
    controller = await kuka.add_folder(idx, "Robot_Controller")
    ctrl_status = await controller.add_variable(
    ua.NodeId("Kuka_Robot/Robot_Controller/Status", idx), 
    "Status", 
    "READY"
    )
    
    # Component: Energy_Measurement (WAGO 750-493)
    energy = await kuka.add_folder(idx, "Energy_Measurement")
    power_consumption = await energy.add_variable(
    ua.NodeId("Kuka_Robot/Energy_Measurement/Power_W", idx),
    "Power_W", 
    0.0
    )   
    await power_consumption.set_writable()

    # Component: Robot_Gripper 
    gripper = await kuka.add_folder(idx, "Robot_Gripper")
    is_closed = await gripper.add_variable(
    ua.NodeId("Kuka_Robot/Robot_Gripper/Is_Closed", idx),
    "Is_Closed", 
    False
    )

    # Start Server
    print(f"Kuka Robot Simulator started at opc.tcp://0.0.0.0:4849")
    async with server:
        while True:
            # Simulate dynamic energy data
            new_power = round(random.uniform(1.2, 5.5), 2)
            await power_consumption.write_value(new_power)
            
            # Simulate gripper cycle
            await is_closed.write_value(not (await is_closed.get_value()))
            print(f"Power: {new_power} W | Gripper: {await is_closed.get_value()}")
            await asyncio.sleep(2)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())