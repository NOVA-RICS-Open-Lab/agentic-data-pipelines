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


load_dotenv(override=True)
print("OPENAI_API_KEY loaded:", os.getenv("OPENAI_API_KEY") is not None)

openai = OpenAI()


#AAS MESSAGE BUFFER 


AAS_SERVER_URL = "http://localhost:5001/api/v3.0"
#AAS_IDSHORT = "CarASS"

AAS_MESSAGES = deque(maxlen=200)
AAS_LOCK = threading.Lock()

def record_aas_message(topic: str, payload: str):
    with AAS_LOCK:
        AAS_MESSAGES.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "topic": topic,
            "payload": payload,
        })

def format_recent(n: int = 10) -> str:
    with AAS_LOCK:
        msgs = list(AAS_MESSAGES)[-n:]
    if not msgs:
        return "No AAS messages received yet."
    lines = [f"[{m['ts']}] {m['topic']} -> {m['payload']}" for m in msgs]
    return "\n".join(lines)



#FASTAPI APP  for Rest

api = FastAPI()

class AASPayload(BaseModel):
    topic: str | None = None
    payload: str

@api.post("/aas")
async def receive_aas(msg: AASPayload):
    
    topic = msg.topic or "AAS/unknown"
    payload = msg.payload


    record_aas_message(topic, payload)

    prompt = (
        "Incoming AASX message.\n"
        f"Topic: {topic}\n"
        f"Payload: {payload}\n\n"
        "Explain this in a clear, easy-to-understand way for a human."
    )

    try:
        result = await Runner.run(agent, prompt)
        reply = result.final_output
    except Exception as e:
        reply = f"Agent error: {e}"

    return {"reply": reply}

##Gradio

async def chat(messages, history):

    # Normalize latest user message
    if isinstance(messages, str):
        last_user = messages
    elif isinstance(messages, list):
        last_user = ""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                last_user = m.get("content", "")
                break
    else:
        last_user = str(messages)

    text = last_user.strip()
    lower = text.lower()

    # Quick commands to inspect buffered AAS messages
    if lower in {"show recent", "recent", "what have you read?", "list"}:
        return {"role": "assistant", "content": format_recent(10)}

    #direct AAS queries via tools
    if "submodel" in lower:
        answer = _summarise_submodel_list()
        return {"role": "assistant", "content": answer}

    if any(word in lower for word in ["operational", "rpm", "fuel", "tire", "speed", "engine temperature"]):
        answer =  _summarise_operational_data()
        return {"role": "assistant", "content": answer}
      

    # Otherwise, answer using recent AAS message context via the Agent
    recent_context = format_recent(20)
    prompt = (
        "Context: You are monitoring an AASX system via REST messages. "
        "Here are the most recent messages that have arrived:\n"
        f"{recent_context}\n\n"
        f"User question: {last_user}\n\n"
        "Answer clearly, using the context where relevant. "
        "If the context doesn't contain the requested info, say so."
    )

    try:
        result = await Runner.run(agent, prompt)
        reply = result.final_output
    except Exception as e:
        reply = f"Agent error: {e}"

    return {"role": "assistant", "content": reply}

interface = gr.ChatInterface(
    fn=chat,
    ###type="messages",  ##Atualização do gradio para 6.0 deixou de ser necessário
)



##"Ferramentas" para as tools

def _encode_id_for_path(raw_id: str) -> str:
    """Base64url-encode an AAS/Submodel ID as used in AasxServerBlazor URLs."""
    encoded = base64.urlsafe_b64encode(raw_id.encode("utf-8")).decode("utf-8")
    return encoded.rstrip("=")


def _list_all_aas() -> list[dict]:
    """
    List all Asset Administration Shells from the AAS API (Blazor server).
    Uses /shells, which is part of the V3 HTTP API.
    """
    url = f"{AAS_SERVER_URL}/shells"
    print(f"DEBUG: Listing AAS shells from: {url}")

    try:
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=5)

        resp.raise_for_status()
        data = resp.json()

        # V3 API usually wraps results in { "result": [...] }
        if isinstance(data, dict) and "result" in data:
            shells = data["result"]
        elif isinstance(data, list):
            shells = data
        else:
            print(f"DEBUG: Unexpected /shells structure: {data}")
            return []

        print(f"DEBUG: Found {len(shells)} shells")
        return shells

    except Exception as e:
        print(f"ERROR: Failed to list AAS shells: {e}")
        return []

def _get_submodel_list(aas_id: str | None = None) -> list[dict]:
    """
    Return the raw JSON list of submodels.

    NOTE: For this AASXServerBlazor setup we use the global /submodels
    endpoint, because /shells/{id}/submodels returns HTML (UI), not JSON.
    """
    url = f"{AAS_SERVER_URL}/submodels"
    print(f"DEBUG: Getting submodels from: {url}")

    resp = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
    print(f"DEBUG: Status: {resp.status_code}")
    print(f"DEBUG: Content-Type: {resp.headers.get('content-type')}")

    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, dict) and "result" in data:
        return data["result"]
    elif isinstance(data, list):
        return data

    print(f"DEBUG: Unexpected /submodels structure: {data}")
    return []


def _load_submodel_by_idshort(id_short: str, aas_id: str | None = None) -> dict | None:
    """Find a submodel by idShort and return its full JSON."""
    submodels = _get_submodel_list(aas_id)
    if not submodels:
        print("DEBUG: No submodels found")
        return None

    raw_id = None
    for sm in submodels:
        if sm.get("idShort") == id_short:
            raw_id = sm.get("id")
            break

    if not raw_id:
        available = [sm.get("idShort", "unknown") for sm in submodels]
        print(f"DEBUG: Submodel '{id_short}' not found. Available: {available}")
        return None

    encoded_id = _encode_id_for_path(raw_id)
    url = f"{AAS_SERVER_URL}/submodels/{encoded_id}"
    print(f"DEBUG: Fetching submodel from: {url}")

    try:
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
        if resp.status_code == 404:
            # Try alternative path used by some servers
            url_alt = f"{AAS_SERVER_URL}/submodels/{encoded_id}/submodel"
            print(f"DEBUG: Trying alternative: {url_alt}")
            resp = requests.get(url_alt, headers={"Accept": "application/json"}, timeout=5)

        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"ERROR: Failed to fetch submodel '{id_short}': {e}")
        return None


def _summarise_operational_data(aas_id: str = None) -> str:
    """Return a friendly text summary of the OperationalData submodel."""
    sm = _load_submodel_by_idshort("OperationalData", aas_id)
    if sm is None:
        return "Submodel 'OperationalData' not found on the AAS server."

    elems = sm.get("submodelElements", [])
    values: dict[str, str] = {}
    for el in elems:
        id_short = el.get("idShort")
        if not id_short:
            continue
        values[id_short] = el.get("value")

    rpm = values.get("RPM", "unknown")
    fuel = values.get("FuelLoad", "unknown")
    tire = values.get("TirePressure", "unknown")
    temp = values.get("EngineTemperature", "unknown")
    speed = values.get("Speed", "unknown")

    return (
        "OperationalData values:\n"
        f"- RPM: {rpm}\n"
        f"- FuelLoad: {fuel}\n"
        f"- TirePressure: {tire}\n"
        f"- EngineTemperature: {temp}\n"
        f"- Speed: {speed}"
    )


def _summarise_submodel_list(aas_id: str = None) -> str:
    """Return a friendly text summary of all submodels."""
    try:
        submodels = _get_submodel_list(aas_id)
    except requests.HTTPError as e:
        return f"HTTP error while listing submodels: {e}"
    except Exception as e:
        return f"Failed to connect to AAS server: {e}"

    if not submodels:
        # Try to list AAS first to help debug
        all_aas = _list_all_aas()
        if all_aas:
            aas_names = [aas.get('idShort', aas.get('id', 'unknown')) for aas in all_aas]
            return f"Found AAS: {', '.join(aas_names)}, but no submodels found."
        return "No AAS or submodels found on the server."

    lines = ["Submodels found:"]
    for sm in submodels:
        lines.append(
            f"- idShort='{sm.get('idShort')}', id='{sm.get('id')}'"
        )
    return "\n".join(lines)



##Ferramentas

@function_tool
def list_submodels():
    """
    List all submodels for the CarASS AAS.
    Returns a human-friendly summary with idShort and raw IDs.
    """
    return _summarise_submodel_list()


@function_tool
def read_submodel(submodel_name: str):
    """
    Fetch the full JSON content of a specific submodel by its idShort
    (e.g. 'Nameplate V3.0', 'OperationalData').
    """
    try:
        data = _load_submodel_by_idshort(submodel_name)
    except requests.HTTPError as e:
        return f"HTTP error while reading submodel '{submodel_name}': {e}"
    except Exception as e:
        return f"Failed to read submodel '{submodel_name}': {e}"

    if data is None:
        return f"Submodel with idShort '{submodel_name}' not found."

    return json.dumps(data, indent=2)


@function_tool
def read_all_submodels():
    """
    Fetch the JSON content of all submodels for CarASS.
    Returns one JSON object keyed by idShort.
    """
    try:
        submodels = _get_submodel_list()
    except requests.HTTPError as e:
        return f"HTTP error while listing submodels: {e}"
    except Exception as e:
        return f"Failed to connect to AAS server: {e}"

    if not submodels:
        return "No submodels found for CarASS."

    result: dict[str, dict] = {}
    for sm in submodels:
        id_short = sm.get("idShort")
        raw_id = sm.get("id")
        if not id_short or not raw_id:
            continue

        try:
            encoded_id = _encode_id_for_path(raw_id)
            url = f"{AAS_SERVER_URL}/submodels/{encoded_id}/submodel"
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
            r.raise_for_status()
            result[id_short] = r.json()
        except Exception as e:
            result[id_short] = {"error": str(e)}

    return json.dumps(result, indent=2)


@function_tool
def get_operational_values():
    """
    Reads the 'OperationalData' submodel and returns the current values
    of RPM, FuelLoad, TirePressure, EngineTemperature and Speed in a
    human-friendly text format.
    """
    try:
        return _summarise_operational_data()
    except requests.HTTPError as e:
        return f"HTTP error while reading OperationalData: {e}"
    except Exception as e:
        return f"Failed to read OperationalData: {e}"

##Agent
listener_ai_prompt = ( ##MELJORAR
    "You are a listener, whose job it is to listen to an AASX "
    "(Asset Administration Shell Explorer) system. You also have tools that can "
    "query the AAS server directly (list_submodels, read_submodel, "
    "read_all_submodels, get_operational_values). "
    "Whenever the user asks about submodels or operational values, "
    "you MUST call the appropriate tools instead of guessing."
)

agent = Agent(
    name="Listener",
    instructions=listener_ai_prompt,
    model="gpt-4o-mini",
    tools=[list_submodels,
        read_submodel,
        read_all_submodels,
        get_operational_values
        ,]
    )

def main():
    #Start REST API
    def run_api():
        uvicorn.run(api, host="0.0.0.0", port=8000, log_level="info")

    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()

    #Start Gradio UI
    interface.launch(server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    main()
    
