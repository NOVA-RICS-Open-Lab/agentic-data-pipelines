import asyncio
from dotenv import load_dotenv
import os
from openai import OpenAI
from agents import Agent, Runner, function_tool
import gradio as gr
from collections import deque
from datetime import datetime
import threading

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import requests
import base64
import json
from urllib.parse import quote

load_dotenv(override=True)
openai = OpenAI()

# CONFIGURATION
AAS_SERVER_URL = "http://localhost:5001/api/v3.0"



def _encode_base64(s: str) -> str:
    """Base64url-encode a string (ID) for URL usage (RFC 4648)."""
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8").rstrip("=")

##Tools

@function_tool
def list_available_assets():
    """
    Lists all Asset Administration Shells (AAS) currently on the server.
    """
    try:
        url = f"{AAS_SERVER_URL}/shells"
        print(f"[API] Requesting: GET {url}")
        
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        shells = data.get("result", data)
        
        lines = []
        for s in shells:
            lines.append(f"- Name: {s.get('idShort')} (ID: {s.get('id')})")
        
        return "\n".join(lines) if lines else "No AAS found."
    except Exception as e:
        return f"Error listing assets: {e}"

@function_tool
def find_submodel_directly(submodel_name: str):
    """
    Searches the GLOBAL list of submodels for one with a matching name.
    """
    try:
        url = f"{AAS_SERVER_URL}/submodels"
        print(f"[API] Requesting: GET {url}")
        
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
        resp.raise_for_status()
        
        data = resp.json()
        submodels = data.get("result", data)
        
        matches = []
        for sm in submodels:
            sm_id_short = sm.get("idShort", "")
            if submodel_name.lower() in sm_id_short.lower():
                matches.append(f"- Found Submodel: {sm_id_short}")
                matches.append(f"  Exact ID: {sm.get('id')}") 
                
                # Peek inside to see elements
                elements = sm.get("submodelElements", [])
                elem_names = [f"{e.get('idShort')} ({e.get('modelType')})" for e in elements]
                if elem_names:
                    matches.append(f"  Contains: {', '.join(elem_names)}")

        if not matches:
            return f"No submodel found matching '{submodel_name}'."
            
        return "\n".join(matches)
        
    except Exception as e:
        return f"Error scanning submodels: {e}"

@function_tool
def update_aas_value(submodel_name: str, element_path: str, value: str):
    """
    Updates a value by retrieving the full element, modifying it, and sending it back.
    This works around the 'Body is null' error on Blazor servers.
    """
    print(f"[Agent] Updating {submodel_name} -> {element_path} = {value}")

    # 1. FIND THE SUBMODEL ID
    sm_id = None
    target_sm_name = submodel_name
    
    try:
        url = f"{AAS_SERVER_URL}/submodels"
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
        if resp.ok:
            data = resp.json()
            submodels = data.get("result", data)
            for sm in submodels:
                if submodel_name.lower() in sm.get("idShort", "").lower():
                    sm_id = sm.get("id")
                    target_sm_name = sm.get("idShort")
                    break
    except Exception as e:
        return f"Connection error: {e}"

    if not sm_id:
        return f"Error: Submodel '{submodel_name}' not found on server."

    print(f"[Agent] Using Submodel ID: {sm_id}")

    # 2. PERFORM  UPDATE (GET -> MODIFY -> PUT)
    try:
        encoded_submodel = _encode_base64(sm_id)
        id_short_path = quote(element_path, safe="[]().")
        
        
        element_url = (
            f"{AAS_SERVER_URL}/submodels/"
            f"{encoded_submodel}/submodel-elements/{id_short_path}"
        )

        # Step A: GET the full element JSON
        print(f"[API] GET {element_url}")
        r_get = requests.get(element_url, headers={"Accept": "application/json"}, timeout=5)
        
        if not r_get.ok:
            return f"Error retrieving element: {r_get.status_code} - {r_get.text}"
            
        element_data = r_get.json()
        print(f"[API] Retrieved Element: {element_data.get('idShort')} (Type: {element_data.get('modelType')})")

        # Step B: Modify the value in the JSON object
        
        if "value" in element_data:
            element_data["value"] = str(value)
        else:
            # Fallback for other element types if necessary, but usually it's 'value'
            return f"Error: The element '{element_path}' does not have a direct 'value' field."

        # Step C: PUT the full JSON object back
        print(f"[API] PUT {element_url} | Payload: Full JSON Object")
        
        
        r_put = requests.put(element_url, json=element_data, timeout=5)

        if r_put.ok:
            return f"Success: Updated '{target_sm_name}/{element_path}' to '{value}'"
        else:
            return f"Failed to update (HTTP {r_put.status_code}): {r_put.text}"

    except Exception as e:
        return f"Update exception: {e}"

#AGENT SETUP

prompt = (
    "You are the 'AAS Manipulator'. "
    "You update AAS values using a robust Get-Modify-Put strategy. "
    "Behavior:\n"
    "1. When updating (e.g. 'Set Speed'), ignore Shell links.\n"
    "2. Use 'find_submodel_directly' to confirm the submodel exists (e.g. 'OperationalData').\n"
    "3. Use 'update_aas_value' to perform the update.\n"
    "4. Always verify casing (e.g. 'Speed' vs 'speed')."
)

agent = Agent(
    name="Populater",
    instructions=prompt,
    model="gpt-4o-mini",
    tools=[list_available_assets, find_submodel_directly, update_aas_value]
)

##GRADIO

async def chat(message, history):
    try:
        result = await Runner.run(agent, message)
        return result.final_output
    except Exception as e:
        return f"Agent Error: {e}"

interface = gr.ChatInterface(
    fn=chat,
    title="Universal AAS Populater",
)

async def main():
    print("--- AAS Populater Started ---")
    interface.launch(server_name="0.0.0.0", server_port=7861) #7860 esta o listener para ja

if __name__ == "__main__":
    asyncio.run(main())