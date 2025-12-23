import gradio as gr
from src.agents import SystemAgent


async def run(message, history):
    sys_agent = SystemAgent()

    if history is None:
        history = []

    # Append user message
    history = history + [{"role": "user", "content": message}]
    yield history

    assistant_text = ""

    async for token in sys_agent.run_with_mcp_servers_streamed(message):
        assistant_text += token

        # Update assistant message
        if len(history) == 0 or history[-1]["role"] != "assistant":
            history.append({"role": "assistant", "content": assistant_text})
        else:
            history[-1]["content"] = assistant_text

        yield history


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