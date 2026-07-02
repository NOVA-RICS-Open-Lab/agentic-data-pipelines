from fastapi.testclient import TestClient
from src.a2a.host import create_a2a_app

def test_a2a_host_info():
    card = {"name": "TestAgent"}
    app = create_a2a_app(card, lambda x: "result")
    client = TestClient(app)
    response = client.get("/info")
    assert response.status_code == 200
    assert response.json() == card

def test_a2a_host_rpc():
    async def mock_handler(params):
        return {"processed": params["input"]}
    
    card = {"name": "TestAgent"}
    app = create_a2a_app(card, mock_handler)
    client = TestClient(app)
    
    payload = {
        "jsonrpc": "2.0",
        "method": "test",
        "params": {"input": "hello"},
        "id": "1"
    }
    response = client.post("/rpc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["result"] == {"processed": "hello"}
    assert data["id"] == "1"
