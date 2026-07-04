import datetime
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_master_token
from ..models import Token
from ..rabbitmq_utils import send_command_to_rabbitmq
from ..runtime import RABBITMQ_INPUT_QUEUE, RABBITMQ_PARAMETERS, error_logger
from ..schemas import CommandMasterRequest, CommandRequest, TokenRequest, TokenResponse

router = APIRouter()


@router.post("/token", response_model=TokenResponse)
def issue_temp_token(
    req: TokenRequest,
    master_token=Depends(require_master_token),
    db: Session = Depends(get_db),
):
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
        context_id=req.context_id,
    )
    db.add(temp_token)
    db.commit()

    return TokenResponse(
        token=temp_token_str,
        expires_at=req.expires_at,
        max_uses=req.max_uses,
        context_id=req.context_id,
    )


@router.post("/command")
def post_command(req: CommandRequest, db: Session = Depends(get_db)):
    token_str = req.token
    now = datetime.datetime.utcnow()

    temp_token: Token = db.query(Token).filter(Token.token == token_str).first()
    context_id = ""

    if temp_token:
        if temp_token.expires_at and temp_token.expires_at < now:
            error_logger.log_error("Expired temporary token", responsibility="vps_api")
            raise HTTPException(status_code=401, detail="Token expired")
        if temp_token.max_uses and temp_token.usage_count >= temp_token.max_uses:
            error_logger.log_error("Token usage limit exceeded", responsibility="vps_api")
            raise HTTPException(status_code=401, detail="Token usage limit exceeded")

        temp_token.usage_count = (temp_token.usage_count or 0) + 1
        temp_token.last_used_at = now
        db.commit()
        context_id = temp_token.context_id or ""
    else:
        error_logger.log_error("Invalid token", responsibility="vps_api")
        raise HTTPException(status_code=401, detail="Invalid token")

    msg = {
        "source": {"system": "vps_api", "context_id": context_id},
        "system": "API",
        "command_name": req.command_name,
        "command_params": req.command_params,
    }
    try:
        send_command_to_rabbitmq(RABBITMQ_INPUT_QUEUE, msg, RABBITMQ_PARAMETERS)
    except Exception as exc:
        error_logger.log_error(f"RabbitMQ error: {exc}", responsibility="vps_api")
        raise HTTPException(status_code=500, detail="Failed to send command")

    return {"status": "ok"}


@router.post("/command/master")
def post_command_master(
    req: CommandMasterRequest,
    _master_token=Depends(require_master_token),
):
    msg = {
        "source": {"system": "vps_api", "context_id": ""},
        "system": "API",
        "command_name": req.command_name,
        "command_params": req.command_params,
    }

    try:
        send_command_to_rabbitmq(RABBITMQ_INPUT_QUEUE, msg, RABBITMQ_PARAMETERS)
    except Exception as exc:
        error_logger.log_error(f"RabbitMQ error: {exc}", responsibility="vps_api")
        raise HTTPException(status_code=500, detail="Failed to send command")

    return {"status": "ok"}
