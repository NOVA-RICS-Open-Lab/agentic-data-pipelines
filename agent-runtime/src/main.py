import gradio as gr
from src.agents import SystemAgent # type: ignore
import logging
import sys

logging.basicConfig(level=logging.DEBUG, handlers=[
    logging.StreamHandler(sys.stderr)
])

system = SystemAgent()

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

        yield history, ""


with gr.Blocks() as ui:
    gr.Markdown("## Agentic Pipelines Chat Interface")
    chat = gr.Chatbot()
    msg = gr.Textbox()
    msg.submit(run, [msg, chat], [chat, msg])


ui.launch(
    server_name="0.0.0.0",
    server_port=8000,
    theme=gr.themes.Default(primary_hue="sky"), # type: ignore
)
