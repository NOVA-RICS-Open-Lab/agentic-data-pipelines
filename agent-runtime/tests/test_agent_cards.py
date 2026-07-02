from src.agents.cards import ORCHESTRATOR_CARD, RESEARCHER_CARD, GENERATOR_CARD, REVIEWER_CARD

def test_orchestrator_card():
    assert ORCHESTRATOR_CARD["name"] == "OrchestratorAgent"
    assert ORCHESTRATOR_CARD["type"] == "Agent"
    assert "execute_task" in ORCHESTRATOR_CARD["capabilities"]

def test_researcher_card():
    assert RESEARCHER_CARD["name"] == "ResearcherAgent"
    assert RESEARCHER_CARD["type"] == "Agent"
    assert "search" in RESEARCHER_CARD["capabilities"]
    assert "analyze" in RESEARCHER_CARD["capabilities"]

def test_generator_card():
    assert GENERATOR_CARD["name"] == "GeneratorAgent"
    assert GENERATOR_CARD["type"] == "Agent"
    assert "generate_pipeline" in GENERATOR_CARD["capabilities"]
    assert "create_aasx" in GENERATOR_CARD["capabilities"]
    
def test_reviewer_card():
    assert REVIEWER_CARD["name"] == "ReviewerAgent"
    assert REVIEWER_CARD["type"] == "Agent"

