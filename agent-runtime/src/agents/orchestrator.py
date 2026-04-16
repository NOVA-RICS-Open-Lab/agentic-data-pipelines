from agent_squad.classifiers import OpenAIClassifier, OpenAIClassifierOptions
from agent_squad.orchestrator import AgentSquad
from src.config import Templates, Config

openai_classifier = OpenAIClassifier(OpenAIClassifierOptions(
    api_key= Config.get_model
))

orchestrator = AgentSquad(classifier=openai_classifier)