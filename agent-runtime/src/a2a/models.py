from pydantic import BaseModel, Field
from typing import Any, Optional, Union
import uuid

class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[dict] = None
    id: Union[str, int] = Field(default_factory=lambda: str(uuid.uuid4()))

class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None

class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None
    id: Union[str, int, None]
