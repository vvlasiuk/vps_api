import pathlib
from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).parent.parent / ".env", override=True)

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from . import models, schemas
from .database import SessionLocal, engine
from .error_logger import ErrorLogger
from .rabbitmq_utils import send_command_to_rabbitmq
import pika
from .models import Context, ContextStatus, Token, MasterToken, MasterTokenStatus, User
from .schemas import ContextCreate, ContextUpdate, ContextResponse, CommandRequest, CommandMasterRequest, TokenRequest, TokenResponse, UserCreate, UserResponse, UserUpdate, LoginRequest, LoginResponse, OneCQueryRequest, OneCQueryResponse
import os
import datetime
import json
import secrets
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
import httpx
import bcrypt as bcrypt_lib
from . import query_loader

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="VPS API Confirmation Server", debug=True)

query_loader.load_queries()

from fastapi.staticfiles import StaticFiles
app.mount("/html", StaticFiles(directory="html", html=True), name="html")

def hash_password(password: str) -> str:
    return bcrypt_lib.hashpw(password.encode(), bcrypt_lib.gensalt()).decode()
 
def verify_password(password: str, hashed: str) -> bool:
    return bcrypt_lib.checkpw(password.encode(), hashed.encode())

# Dependency to get DB session
def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()

# Error logger instance

ONEC_QUERY_URL = os.getenv("ONEC_QUERY_URL",   "")
ONEC_TOKEN = os.getenv("ONEC_TOKEN", "")
# Формуємо RabbitMQ URL з окремих змінних

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")
RABBITMQ_INPUT_QUEUE = os.getenv("RABBITMQ_INPUT_QUEUE", "input.events")
RABBITMQ_ERROR_QUEUE = os.getenv("RABBITMQ_ERROR_QUEUE", "sys_error.queue")

RABBITMQ_PARAMETERS = pika.ConnectionParameters(
	host=RABBITMQ_HOST,
	port=RABBITMQ_PORT,
	virtual_host=RABBITMQ_VHOST,
	credentials=pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
)

error_logger = ErrorLogger(
	f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/{RABBITMQ_VHOST}",
	queue_name=RABBITMQ_ERROR_QUEUE
)

security = HTTPBearer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # або вкажіть список дозволених доменів
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Context endpoints ---
@app.post("/context", response_model=ContextResponse)
def create_context(
    req: ContextCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    master_token_str = credentials.credentials
    master_token = db.query(MasterToken).filter(
        MasterToken.token == master_token_str,
        MasterToken.status == MasterTokenStatus.active
    ).first()

    if not master_token:
        error_logger.log_error("Invalid or revoked master token", responsibility="vps_api")
        raise HTTPException(status_code=401, detail="Invalid or revoked master token")

    now = datetime.datetime.utcnow()
    ctx = Context(
        object_id=req.object_id,
        context_data=json.dumps(req.context_data),
        created_at=now,
        updated_at=now,
        end_at=req.end_at, closed=False
    )
    try:
        db.add(ctx)
        db.commit()
        db.refresh(ctx)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Context with this object_id already exists")
    return ContextResponse(
        id=ctx.id,
        object_id=ctx.object_id,
        context_data=req.context_data,
        created_at=ctx.created_at,
        updated_at=ctx.updated_at,
        end_at=ctx.end_at, closed=ctx.closed
    )

@app.get("/context/{object_id}", response_model=ContextResponse)
def get_context(object_id: str, db: Session = Depends(get_db)):
	ctx = db.query(Context).filter(Context.object_id == object_id).first()
	if not ctx:
		raise HTTPException(status_code=404, detail="Context not found")
	return ContextResponse(
		id=ctx.id,
		object_id=ctx.object_id,
		context_data=json.loads(ctx.context_data),
		created_at=ctx.created_at,
		updated_at=ctx.updated_at,
		closed=ctx.closed
	)

@app.get("/context_by_id/{id}", response_model=ContextResponse)
def get_context_by_id(id: int, db: Session = Depends(get_db)):
    ctx = db.query(Context).filter(Context.id == id).first()
    if not ctx:
        raise HTTPException(status_code=404, detail="Context not found")
    return ContextResponse(
        id=ctx.id,
        object_id=ctx.object_id,
        context_data=json.loads(ctx.context_data),
        created_at=ctx.created_at,
        updated_at=ctx.updated_at,
        closed=ctx.closed,
        end_at=getattr(ctx, "end_at", None)
    )

@app.put("/context/{object_id}", response_model=ContextResponse)
def update_context(object_id: str, req: ContextUpdate, db: Session = Depends(get_db)):
	ctx = db.query(Context).filter(Context.object_id == object_id).first()
	if not ctx:
		raise HTTPException(status_code=404, detail="Context not found")
	ctx.context_data = json.dumps(req.context_data)
	# if req.status:
	# 	ctx.status = ContextStatus(req.status)
	ctx.updated_at = datetime.datetime.utcnow()
	db.commit()
	db.refresh(ctx)
	return ContextResponse(
		id=ctx.id,
		object_id=ctx.object_id,
		context_data=json.loads(ctx.context_data),
		created_at=ctx.created_at,
		updated_at=ctx.updated_at,
		closed=ctx.closed
	)

@app.post("/context/{id}/close")
def close_context(
    id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    master_token_str = credentials.credentials
    master_token = db.query(MasterToken).filter(
        MasterToken.token == master_token_str,
        MasterToken.status == MasterTokenStatus.active
    ).first()
    if not master_token:
        error_logger.log_error("Invalid or revoked master token", responsibility="vps_api")
        raise HTTPException(status_code=401, detail="Invalid or revoked master token")

    ctx = db.query(Context).filter(Context.id == id).first()
    if not ctx:
        raise HTTPException(status_code=404, detail="Context not found")

    ctx.closed = True
    ctx.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(ctx)
    return {"status": "closed", "id": ctx.id}

# --- /token endpoint ---
@app.post("/token", response_model=TokenResponse)
def issue_temp_token(
	req: TokenRequest,
	credentials: HTTPAuthorizationCredentials = Depends(security),
	db: Session = Depends(get_db)
):
	master_token_str = credentials.credentials
	master_token = db.query(MasterToken).filter(MasterToken.token == master_token_str, MasterToken.status == MasterTokenStatus.active).first()
	if not master_token:
		error_logger.log_error("Invalid or revoked master token", responsibility="vps_api")
		raise HTTPException(status_code=401, detail="Invalid or revoked master token")

	temp_token_str = secrets.token_urlsafe(32)
	now = datetime.datetime.utcnow()
	temp_token = Token(
		token=temp_token_str,
		command_name=None,
		command_params=None,
		created_at=now,
		expires_at=req.expires_at,
		issued_by=master_token.id,
		usage_count=0,
		max_uses=req.max_uses,
		context_id=req.context_id
	)
	db.add(temp_token)
	db.commit()
	return TokenResponse(
		token=temp_token_str,
		expires_at=req.expires_at,
		max_uses=req.max_uses,
		context_id=req.context_id
	)

# --- /command endpoint ---
@app.post("/command")
def post_command(
	req: CommandRequest,
	db: Session = Depends(get_db)
):
	token_str = req.token
	now = datetime.datetime.utcnow()

	# 1) Пробуємо тимчасовий токен
	temp_token: Token = db.query(Token).filter(Token.token == token_str).first()
	context_id = ""

	if temp_token:
		# Чинна валідація для тимчасового токена
		if temp_token.expires_at and temp_token.expires_at < now:
			error_logger.log_error("Expired temporary token", responsibility="vps_api")
			raise HTTPException(status_code=401, detail="Token expired")
		if temp_token.max_uses and temp_token.usage_count >= temp_token.max_uses:
			error_logger.log_error("Token usage limit exceeded", responsibility="vps_api")
			raise HTTPException(status_code=401, detail="Token usage limit exceeded")

		# Update usage only for temp token
		temp_token.usage_count = (temp_token.usage_count or 0) + 1
		temp_token.last_used_at = now
		db.commit()
		context_id = temp_token.context_id or ""
	else:
		error_logger.log_error("Invalid token", responsibility="vps_api")
		raise HTTPException(status_code=401, detail="Invalid token")    

	# Формуємо повідомлення для input.queue
	msg = {
		"source": {
			"system": "vps_api",
			"context_id": context_id
		},
		"system": "API",
		"command_name": req.command_name,
		"command_params": req.command_params
	}
	try:
		send_command_to_rabbitmq(RABBITMQ_INPUT_QUEUE, msg, RABBITMQ_PARAMETERS)
	except Exception as e:
		error_logger.log_error(f"RabbitMQ error: {e}", responsibility="vps_api")
		raise HTTPException(status_code=500, detail="Failed to send command")

	return {"status": "ok"}

# --- /command/master endpoint ---
@app.post("/command/master")
def post_command_master(
    req: CommandMasterRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    master_token_str = credentials.credentials
    master_token = db.query(MasterToken).filter(
        MasterToken.token == master_token_str,
        MasterToken.status == MasterTokenStatus.active
    ).first()

    if not master_token:
        error_logger.log_error("Invalid or revoked master token", responsibility="vps_api")
        raise HTTPException(status_code=401, detail="Invalid or revoked master token")

    msg = {
        "source": {
            "system": "vps_api",
            "context_id": ""
        },
        "system": "API",
        "command_name": req.command_name,
        "command_params": req.command_params
    }

    try:
        send_command_to_rabbitmq(RABBITMQ_INPUT_QUEUE, msg, RABBITMQ_PARAMETERS)
    except Exception as e:
        error_logger.log_error(f"RabbitMQ error: {e}", responsibility="vps_api")
        raise HTTPException(status_code=500, detail="Failed to send command")

    return {"status": "ok"}

# --- /user endpoint ---
@app.post("/users", response_model=UserResponse)
def create_user(
    req: UserCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    master_token_str = credentials.credentials
    master_token = db.query(MasterToken).filter(
        MasterToken.token == master_token_str,
        MasterToken.status == MasterTokenStatus.active
    ).first()

    if not master_token:
        error_logger.log_error("Invalid or revoked master token", responsibility="vps_api")
        raise HTTPException(status_code=401, detail="Invalid or revoked master token")

    now = datetime.datetime.utcnow()

    user = User(
        lastname=req.lastname,
        firstname=req.firstname,
        middlename=req.middlename,
        position=req.position,
        department=req.department,
        city=req.city,
        phone=req.phone,
        email=req.email,
        chat_id=req.chat_id,
        role=req.role,
        username=req.username,
        password=hash_password(req.password) if req.password else None,
        is_active=req.is_active,
        created_at=now
    )

    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(
        id=user.id,
        lastname=user.lastname,
        firstname=user.firstname,
        middlename=user.middlename,
        position=user.position,
        department=user.department,
        city=user.city,
        phone=user.phone,
        email=user.email,
        chat_id=user.chat_id,
        role=user.role,
        username=user.username,
        is_active=user.is_active,
        created_at=user.created_at
    )

@app.put("/users/{id}", response_model=UserResponse)
def update_user(
    id: int,
    req: UserUpdate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    master_token_str = credentials.credentials
    master_token = db.query(MasterToken).filter(
        MasterToken.token == master_token_str,
        MasterToken.status == MasterTokenStatus.active
    ).first()

    if not master_token:
        error_logger.log_error("Invalid or revoked master token", responsibility="vps_api")
        raise HTTPException(status_code=401, detail="Invalid or revoked master token")

    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.lastname   is not None: user.lastname   = req.lastname
    if req.firstname  is not None: user.firstname  = req.firstname
    if req.middlename is not None: user.middlename = req.middlename
    if req.position   is not None: user.position   = req.position
    if req.department is not None: user.department = req.department
    if req.city       is not None: user.city       = req.city
    if req.phone      is not None: user.phone      = req.phone
    if req.email      is not None: user.email      = req.email
    if req.chat_id    is not None: user.chat_id    = req.chat_id
    if req.role       is not None: user.role       = req.role
    if req.username   is not None: user.username   = req.username
    if req.is_active  is not None: user.is_active  = req.is_active
    if req.password is not None: user.password = hash_password(req.password)

    db.commit()
    db.refresh(user)
    return UserResponse(
        id=user.id,
        lastname=user.lastname,
        firstname=user.firstname,
        middlename=user.middlename,
        position=user.position,
        department=user.department,
        city=user.city,
        phone=user.phone,
        email=user.email,
        chat_id=user.chat_id,
        role=user.role,
        username=user.username,
        is_active=user.is_active,
        created_at=user.created_at,
    )

# Додати після POST /users в main.py

@app.get("/users", response_model=list[UserResponse])
def get_users(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    master_token_str = credentials.credentials
    master_token = db.query(MasterToken).filter(
        MasterToken.token == master_token_str,
        MasterToken.status == MasterTokenStatus.active
    ).first()

    if not master_token:
        error_logger.log_error("Invalid or revoked master token", responsibility="vps_api")
        raise HTTPException(status_code=401, detail="Invalid or revoked master token")

    users = db.query(User).order_by(User.lastname).all()
    return [
        UserResponse(
            id=u.id,
            lastname=u.lastname,
            firstname=u.firstname,
            middlename=u.middlename,
            position=u.position,
            department=u.department,
            city=u.city,
            phone=u.phone,
            email=u.email,
            chat_id=u.chat_id,
            role=u.role,
            username=u.username,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]
@app.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
 
    user = db.query(User).filter(
        User.username == req.username,
        User.is_active == True
    ).first()
 
    if not user or not user.password:
        raise HTTPException(status_code=401, detail="Невірний логін або пароль")
 
    if not verify_password(req.password, user.password):
        raise HTTPException(status_code=401, detail="Невірний логін або пароль")
 
    now = datetime.datetime.utcnow()
    expires_at = now + datetime.timedelta(hours=8)
 
    token_str = secrets.token_urlsafe(32)
    token = Token(
        token=token_str,
        created_at=now,
        expires_at=expires_at,
        max_uses=99999,
        usage_count=0,
        context_id=str(user.id),
    )
    db.add(token)
    db.commit()
 
    return LoginResponse(
        token=token_str,
        expires_at=expires_at,
        user_id=user.id,
        username=user.username,
        role=user.role,
    )

@app.post("/1c/query", response_model=OneCQueryResponse)
def onec_query(
    req: OneCQueryRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token_str = credentials.credentials
    now = datetime.datetime.utcnow()
 
    # Перевірка токену сесії
    token = db.query(Token).filter(Token.token == token_str).first()
    if not token:
        raise HTTPException(status_code=401, detail="Невірний токен")
    if token.expires_at and token.expires_at < now:
        raise HTTPException(status_code=401, detail="Токен застарів")
    if token.max_uses and token.usage_count >= token.max_uses:
        raise HTTPException(status_code=401, detail="Перевищено ліміт використань")
 
    token.usage_count = (token.usage_count or 0) + 1
    token.last_used_at = now
    db.commit()
 
    # Знаходимо запит у конфігу
    cfg = query_loader.get_query(req.query)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Запит '{req.query}' не знайдено")
 
    inner_query = cfg["query"]
 
    # Поля результату: перелік або всі
    fields_sql = ", ".join(req.fields) if req.fields else "*"
 
    # Обгортаємо внутрішній запит у підзапит, накладаємо поля/відбір/сортування
    wrapped = f"ВЫБРАТЬ {fields_sql}\nИЗ (\n{inner_query}\n) КАК Вложенный"
 
    if req.filters:
        wrapped += f"\nГДЕ {req.filters}"
 
    if req.order:
        wrapped += f"\nУПОРЯДОЧИТЬ ПО {req.order}"
 
    # Параметри для 1С (з filters)
    onec_params = {}
    if req.params:
        for key, p in req.params.items():
            onec_params[key] = {"type": p.type, "value": p.value}
 
    payload = {
        "token":  ONEC_TOKEN,
        "query":  wrapped,
        "params": onec_params,
        "offset": req.offset,
        "limit":  req.limit,
    }
 
    try:
        response = httpx.post(ONEC_QUERY_URL, json=payload, timeout=30)
    except httpx.RequestError as e:
        error_logger.log_error(f"1С недоступний: {e}", responsibility="vps_api")
        raise HTTPException(status_code=503, detail="1С сервіс недоступний")
 
    if response.status_code == 401:
        raise HTTPException(status_code=502, detail="Помилка авторизації до 1С")
 
    if response.status_code != 200:
        data = response.json()
        raise HTTPException(status_code=502, detail=data.get("error", "Помилка 1С"))
 
    return response.json()

# --- GlobalMessageContext endpoints ---

@app.post("/global_message_context/", response_model=schemas.GlobalMessageContextRead)
def create_global_message_context(
    item: schemas.GlobalMessageContextCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    master_token_str = credentials.credentials
    master_token = db.query(MasterToken).filter(
        MasterToken.token == master_token_str,
        MasterToken.status == MasterTokenStatus.active
    ).first()
    if not master_token:
        error_logger.log_error("Invalid or revoked master token", responsibility="vps_api")
        raise HTTPException(status_code=401, detail="Invalid or revoked master token")
    db_item = models.GlobalMessageContext(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@app.get("/global_message_context/", response_model=list[schemas.GlobalMessageContextRead])
def read_global_message_contexts(
    global_msg_id: int | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    master_token_str = credentials.credentials
    master_token = db.query(MasterToken).filter(
        MasterToken.token == master_token_str,
        MasterToken.status == MasterTokenStatus.active
    ).first()
    if not master_token:
        error_logger.log_error("Invalid or revoked master token", responsibility="vps_api")
        raise HTTPException(status_code=401, detail="Invalid or revoked master token")
    query = db.query(models.GlobalMessageContext)
    if global_msg_id is not None:
        query = query.filter(models.GlobalMessageContext.global_msg_id == global_msg_id)
    return query.all()

@app.post("/global_message_telegram/", response_model=schemas.GlobalMessageTelegramRead)
def create_global_message_telegram(
    item: schemas.GlobalMessageTelegramCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    master_token_str = credentials.credentials
    master_token = db.query(MasterToken).filter(
        MasterToken.token == master_token_str,
        MasterToken.status == MasterTokenStatus.active
    ).first()
    if not master_token:
        error_logger.log_error("Invalid or revoked master token", responsibility="vps_api")
        raise HTTPException(status_code=401, detail="Invalid or revoked master token")
    db_item = models.GlobalMessageTelegram(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@app.get("/global_message_telegram/", response_model=list[schemas.GlobalMessageTelegramRead])
def read_global_message_telegrams(
    global_msg_id: int | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    master_token_str = credentials.credentials
    master_token = db.query(MasterToken).filter(
        MasterToken.token == master_token_str,
        MasterToken.status == MasterTokenStatus.active
    ).first()
    if not master_token:
        error_logger.log_error("Invalid or revoked master token", responsibility="vps_api")
        raise HTTPException(status_code=401, detail="Invalid or revoked master token")
    query = db.query(models.GlobalMessageTelegram)
    if global_msg_id is not None:
        query = query.filter(models.GlobalMessageTelegram.global_msg_id == global_msg_id)
    return query.all()

