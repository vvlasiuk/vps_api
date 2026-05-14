from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from . import models, schemas
from .database import SessionLocal
from .error_logger import ErrorLogger
from .rabbitmq_utils import send_command_to_rabbitmq
import pika
from .models import Context, ContextStatus, Token, MasterToken, MasterTokenStatus, User
from .schemas import ContextCreate, ContextUpdate, ContextResponse, CommandRequest, CommandMasterRequest, TokenRequest, TokenResponse, UserCreate, UserResponse
import os
import datetime
import json
import secrets
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError

app = FastAPI(title="VPS API Confirmation Server", debug=True)

# Dependency to get DB session
def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()

# Error logger instance

# Формуємо RabbitMQ URL з окремих змінних

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")
RABBITMQ_INPUT_QUEUE = os.getenv("RABBITMQ_INPUT_QUEUE", "input.queue")
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
        created_at=user.created_at
    )

