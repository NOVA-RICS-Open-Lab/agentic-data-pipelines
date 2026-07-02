import pytest
from unittest.mock import AsyncMock, patch
from src.a2a.client import A2AClient
from src.a2a.models import JSONRPCResponse, JSONRPCError

@pytest.mark.anyio
async def test_a2a_client_call_success():
    base_url = "http://test-agent"
    client = A2AClient(base_url)
    
    expected_result = {"status": "ok"}
    mock_response_data = {
        "jsonrpc": "2.0",
        "result": expected_result,
        "id": "123"
    }
    
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_response_data
        )
        
        result = await client.call("test_method", {"param1": "value1"})
        
        assert result == expected_result
        mock_post.assert_called_once()
        # Verify URL and JSON body
        args, kwargs = mock_post.call_args
        assert args[0] == f"{base_url}/rpc"
        assert kwargs["json"]["method"] == "test_method"
        assert kwargs["json"]["params"] == {"param1": "value1"}

@pytest.mark.anyio
async def test_a2a_client_call_error():
    base_url = "http://test-agent"
    client = A2AClient(base_url)
    
    mock_response_data = {
        "jsonrpc": "2.0",
        "error": {"code": -32601, "message": "Method not found"},
        "id": "123"
    }
    
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_response_data
        )

        with pytest.raises(Exception, match=r"RPC Error: {'code': -32601, 'message': 'Method not found', 'data': None}"):
            await client.call("invalid_method", {})

