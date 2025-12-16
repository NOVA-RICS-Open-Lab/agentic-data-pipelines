import gradio as gr
import requests
from src.config import Settings

settings = Settings()

def check_runtime():
    r = requests.get(f"{settings.AGENT_RUNTIME_URL}/health", timeout=5)
    r.raise_for_status()
    return r.json()

with gr.Blocks(title="Agentic AAS Platform") as demo:
    gr.Markdown("## Agentic AAS Platform")
    gr.Markdown("Minimal UI — system logic lives elsewhere.")

    btn = gr.Button("Check Agent Runtime")
    out = gr.JSON()

    btn.click(fn=check_runtime, outputs=out)

demo.launch(server_name="0.0.0.0", server_port=7860)
