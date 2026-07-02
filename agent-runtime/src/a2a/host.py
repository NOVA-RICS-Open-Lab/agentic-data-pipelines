from fastapi import FastAPI, Request
from src.a2a.models import JSONRPCRequest, JSONRPCResponse
import uvicorn
import inspect
import anyio
import logging

logger = logging.getLogger(__name__)

def create_a2a_app(agent_card: dict, task_handler):
    app = FastAPI()

    @app.get("/info")
    async def info():
        return agent_card

    @app.post("/rpc")
    async def rpc(request: JSONRPCRequest):
        logger.info(f"A2A RECV <- RPC Method: {request.method} | ID: {request.id}")
        
        if inspect.iscoroutinefunction(task_handler):
            result = await task_handler(request.params)
        else:
            result = await anyio.to_thread.run_sync(task_handler, request.params)
            
        response = JSONRPCResponse(result=result, id=request.id)
        logger.info(f"A2A SEND -> RPC Response | ID: {response.id}")
        
        return response

    return app
