from src.config import Settings
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel

openai_client = AsyncOpenAI(base_url=Settings.OPENAI_BASE_URL, api_key=Settings.OPENAI_API_KEY)
openrouter_client = AsyncOpenAI(base_url=Settings.OPENROUTER_BASE_URL, api_key=Settings.OPENROUTER_API_KEY)
deepseek_client = AsyncOpenAI(base_url=Settings.DEEPSEEK_BASE_URL, api_key=Settings.DEEPSEEK_API_KEY)
groq_client = AsyncOpenAI(base_url=Settings.GROQ_BASE_URL, api_key=Settings.GROQ_API_KEY)
grok_cliente = AsyncOpenAI(base_url=Settings.GROK_BASE_URL, api_key=Settings.GROK_API_KEY)
gemini_client = AsyncOpenAI(base_url=Settings.GEMINI_BASE_URL, api_key=Settings.GEMINI_API_KEY)

def get_model(model_name: str):
    if "/" in model_name:
        return OpenAIChatCompletionsModel(model=model_name, openai_client=openrouter_client)
    if "openai" in model_name:
        return OpenAIChatCompletionsModel(model=model_name, openai_client=openai_client)
    elif "deepseek" in model_name:
        return OpenAIChatCompletionsModel(model=model_name, openai_client=deepseek_client)
    elif "grok" in model_name:
        return OpenAIChatCompletionsModel(model=model_name, openai_client=groq_client)
    elif "gemini" in model_name:
        return OpenAIChatCompletionsModel(model=model_name, openai_client=gemini_client)
    else:
        return model_name
