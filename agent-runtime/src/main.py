import gradio as gr
from src.agents import SystemAgent
from src.config import Config
from src.mcp import MCPClient


async def run(message, history):
    async with MCPClient() as mcp:
        tools = await mcp.list_tools()
        agent = SystemAgent.create_agent(tools)

        result = await Config.OPENAI_CLIENT.agents.run(
            agent=agent,
            input=message,
            context=history,
        )

        return history + [(message, result.output_text)]


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