import gradio as gr
from src.agents import SystemAgent
from src.utils import LogTracer
from agents import add_trace_processor

async def run(query: str):
    add_trace_processor(LogTracer())
    sys_agent = SystemAgent("System", "gpt-4.1-mini")
    async for chunk in sys_agent.run(query):
        yield chunk

with gr.Blocks(theme=gr.themes.Default(primary_hue="sky")) as ui:
    gr.Markdown("## Agentic Pipelines Chat Interface")
    chat_input = gr.Textbox(label="Ask about your system")
    chat_output = gr.Markdown(label="System Response")
    chat_input.submit(fn=run, inputs=chat_input, outputs=chat_output)

ui.launch(server_name="0.0.0.0", server_port=7860)
