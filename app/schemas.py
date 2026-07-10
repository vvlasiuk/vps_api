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

class OneCValue(BaseModel):
    type: str
    value: Any

class OneCQueryRequest(BaseModel):
    query:   str                                  # ім'я запиту з конфігу, напр. "ref_contractors"
    fields:  Optional[list[str]] = None           # які поля результату повернути (None = всі)
    filters: Optional[str] = None                 # додатковий відбір по аліасах, напр. "name ПОДОБНО &search"
    params:  Optional[Dict[str, OneCValue]] = None  # значення параметрів для filters
    order:   Optional[str] = None                 # сортування по аліасах, напр. "name"
    offset:  int = 0
    limit:   int = 100
    mcp:     bool = False                          # ознака MCP-каналу (фронт не передає). True → перевірка mcp_allowed

class OneCQueryResponse(BaseModel):
    total: int
    rows: list[Dict[str, Any]]   
    total_time: int = 0 

class SaveDocRequest(BaseModel):
    document: str
    ref: str = ""                                      # "" → створення, guid → редагування
    version: str = ""                                  # ВерсияДанных для перевірки актуальності
    date: str                                          # ISO, передається завжди
    action: str = "write"                              # write | post | unpost | mark_delete
    fields: Optional[Dict[str, OneCValue]] = None     # реквізити документа (формат як у query)
    fields_search: Optional[Dict[str, Any]] = None    # іменовані набори для find-or-create (структуру знає 1С)

class SaveDocResponse(BaseModel):
    ref: str
    number: str
    date: Optional[str] = None
    version: str
    posted: bool
    marked: bool    

class MetadataDescribeRequest(BaseModel):
    type: str                                          # "Справочник" | "Документ"
    name: str                                          # ім'я об'єкта, напр. "Контрагенты"

class MetadataQueriesRequest(BaseModel):
    object_type: str                                   # "Справочник" | "Документ"
    object_name: str                                   # ім'я об'єкта, напр. "Контрагенты"

class SaveQueryRequest(BaseModel):
    file_name: str = ""                                # ім'я файлу без розширення; "" → = meta.query_name
    sel: str                                           # текст запиту (.sel)
    meta: Dict[str, Any]                               # вміст .json (джерело правди: query_name, object_type, object_name, fields...)

class QueryGetRequest(BaseModel):
    query_name: str                                    # ідентифікатор запиту для читання сирих .sel/.json

class GenerateQueryRequest(BaseModel):
    object_type: str                                   # "Справочник" | "Документ"
    object_name: str                                   # ім'я об'єкта, напр. "Контрагенты"
    task: str = ""                                      # завдання для AI; "" → механічна болванка
    current_sel: str = ""                              # поточний .sel у редакторі (AI редагує його, якщо є)
    current_meta: Optional[Dict[str, Any]] = None      # поточний .json у редакторі (для редагування)

class BackupCreateRequest(BaseModel):
    set_name: str                                      # псевдонім набору бекапу (напр. "full_html")

class FormReadRequest(BaseModel):
    path: str                                          # відносний шлях у html/, напр. "pages/admin/x.html"

class FormWriteRequest(BaseModel):
    path: str                                          # шлях у html/ (запис дозволено лише в pages/, menu/)
    content: str                                       # повний вміст файлу

class CommandLogRequest(BaseModel):
    cmd:   str                                  # суть команди користувача (укр.), обов'язкове
    desc:  str                                  # короткий ASCII для імені файлу, обов'язкове
    clar:  str = ""                             # уточнення з діалогу
    why:   str = ""                             # мотив, якщо був
    files: Optional[list[str]] = None           # зачеплені артефакти (шляхи від кореня проекту)

class PhotoListRequest(BaseModel):
    object_type: str                            # повний тип 1С: "Документ.X" | "Справочник.Y"
    ref: str

class PhotoDeleteRequest(BaseModel):
    object_type: str                            # повний тип 1С: "Документ.X" | "Справочник.Y"
    ref: str
    name: str