import gradio as gr
from src.agents import MainAgent


async def run(query: str):
    async for chunk in MainAgent.run(query):
        yield chunk


with gr.Blocks(theme=gr.themes.Default(primary_hue="sky")) as ui:
    gr.Markdown("## Agentic Pipelines Chat Interface")
    chat_input = gr.Textbox(label="Ask about your system")
    chat_output = gr.Markdown(label="System Response")
    chat_input.submit(fn=run, inputs=chat_input, outputs=chat_output)

ui.launch(server_name="0.0.0.0", server_port=7860)
