import pytest
from src.a2a.models import JSONRPCRequest, JSONRPCResponse

def test_jsonrpc_models():
    req = JSONRPCRequest(method="execute", params={"task": "test"})
    assert req.jsonrpc == "2.0"
    
    res = JSONRPCResponse(result="done", id=req.id)
    assert res.jsonrpc == "2.0"
