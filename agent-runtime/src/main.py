import gradio as gr
import json
from src.agents import SystemAgent

system = SystemAgent()

try:
    with open("memory.json") as f:
        system.history = json.load(f)

except FileNotFoundError:
    system.history = []


async def run(message, history):
    if history is None:
        history = []

    history.append({"role": "user", "content": message})
    assistant_text = ""

    async for token in system.run(message):
        assistant_text += token
        if len(history) == 0 or history[-1]["role"] != "assistant":
            history.append({"role": "assistant", "content": assistant_text})
        else:
            history[-1]["content"] = assistant_text

        yield history
    
    with open("memory.json", "w") as f:
        json.dump(system.history, f)


with gr.Blocks() as ui:
    gr.Markdown("## Agentic Pipelines Chat Interface")
    chat = gr.Chatbot()
    msg = gr.Textbox()
    msg.submit(run, [msg, chat], chat)


ui.launch(
    server_name="0.0.0.0",
    server_port=8000,
    theme=gr.themes.Default(primary_hue="sky"),
)
