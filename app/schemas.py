# Pydantic schemas for API requests and responses
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime

class CommandRequest(BaseModel):
    command_name: str
    token: str
    command_params: Dict[str, Any]

class TokenRequest(BaseModel):
    expires_at: datetime
    max_uses: int = Field(..., gt=0)
    context_id: int

class TokenResponse(BaseModel):
    token: str
    expires_at: datetime
    max_uses: int
    context_id: int

class ContextCreate(BaseModel):
    object_id: str
    context_data: Dict[str, Any]
    end_at: Optional[datetime]

class ContextUpdate(BaseModel):
    context_data: Dict[str, Any]
    closed: Optional[bool]
    end_at: Optional[datetime]

class ContextResponse(BaseModel):
    id: int
    object_id: str
    context_data: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    closed: bool
    end_at: Optional[datetime]
