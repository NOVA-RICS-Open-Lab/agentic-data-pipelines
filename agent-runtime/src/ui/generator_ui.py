import gradio as gr
from src.agents import GeneratorAgent
import logging
import sys

logging.basicConfig(level=logging.DEBUG, handlers=[
    logging.StreamHandler(sys.stderr)
])

system = GeneratorAgent()

async def initialize_the_GeneratorAgent():
    await system.initialize()


    
    return "Ready"



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
    gr.Markdown("## Generator Chat Interface")
    status = gr.Markdown('Initializing')
    chat = gr.Chatbot()
    msg = gr.Textbox()
    msg.submit(run, [msg, chat], [chat, msg])
    ui.load(fn=initialize_the_GeneratorAgent, inputs=None, outputs=status)


ui.launch(
    server_name="0.0.0.0",
    server_port=9000,
    theme=gr.themes.Default(primary_hue="sky"), # type: ignore
)
