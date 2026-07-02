import httpx
import logging
from typing import Any
from src.a2a.models import JSONRPCRequest, JSONRPCResponse

logger = logging.getLogger(__name__)

class A2AClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def call(self, method: str, params: dict) -> Any:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            request = JSONRPCRequest(method=method, params=params)
            
            logger.info(f"A2A OUT -> {self.base_url}/a2a/rpc | Method: {method} | ID: {request.id}")
            logger.debug(f"A2A Payload: {request.model_dump_json()}")
            
            response = await client.post(
                f"{self.base_url}/a2a/rpc", 
                json=request.model_dump()
            )
            data = response.json()
            rpc_response = JSONRPCResponse.model_validate(data)
            
            logger.info(f"A2A IN <- {self.base_url}/a2a/rpc | Status: {response.status_code} | ID: {rpc_response.id}")
            
            # Basic error checking
            if rpc_response.error:
                logger.error(f"A2A RPC ERROR: {rpc_response.error.message}")
                raise Exception(f"RPC Error: {rpc_response.error.model_dump()}")
                
            return rpc_response.result
