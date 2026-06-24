# Pydantic schemas for API requests and responses
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime
# import httpx

class CommandRequest(BaseModel):
    command_name: str
    token: str
    command_params: Dict[str, Any]

class CommandMasterRequest(BaseModel):
    command_name: str
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

class UserCreate(BaseModel):
    lastname: Optional[str] = None
    firstname: Optional[str] = None
    middlename: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    chat_id: Optional[str] = None
    role: Optional[str] = None
    username: Optional[str] = None
    created_at: Optional[datetime] = None
    password: Optional[str] = None
    is_active: bool = True

class UserResponse(BaseModel):
    id: int
    lastname: Optional[str] = None
    firstname: Optional[str] = None
    middlename: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    chat_id: Optional[str] = None
    role: Optional[str] = None
    username: Optional[str] = None
    created_at: Optional[datetime] = None
    username: Optional[str] = None
    is_active: bool

class UserUpdate(BaseModel):
    lastname: Optional[str] = None
    firstname: Optional[str] = None
    middlename: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    chat_id: Optional[str] = None
    role: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None

class GlobalMessageContextSchema(BaseModel):
    global_msg_id: int
    context_id: int

class GlobalMessageTelegramSchema(BaseModel):
    global_msg_id: int
    chat_id: int
    message_id: int

class GlobalMessageContextCreate(BaseModel):
    context_id: int | None = None

class GlobalMessageContextRead(BaseModel):
    global_msg_id: int
    context_id: int | None

class GlobalMessageTelegramCreate(BaseModel):
    global_msg_id: int
    chat_id: int | None = None
    message_id: int | None = None

class GlobalMessageTelegramRead(GlobalMessageTelegramCreate):
    id: int

# Додати в кінець schemas.py

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str
    expires_at: datetime
    user_id: int
    username: str
    role: Optional[str] = None    

class QueryParam(BaseModel):
    type: str
    value: Any

class OneCQueryRequest(BaseModel):
    query:   str                                  # ім'я запиту з конфігу, напр. "ref_contractors"
    fields:  Optional[list[str]] = None           # які поля результату повернути (None = всі)
    filters: Optional[str] = None                 # додатковий відбір по аліасах, напр. "name ПОДОБНО &search"
    params:  Optional[Dict[str, QueryParam]] = None  # значення параметрів для filters
    order:   Optional[str] = None                 # сортування по аліасах, напр. "name"
    offset:  int = 0
    limit:   int = 100

class OneCQueryResponse(BaseModel):
    total: int
    rows: list[Dict[str, Any]]    