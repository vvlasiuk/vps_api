import datetime

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import MasterToken, MasterTokenStatus, Token
from .runtime import error_logger

security = HTTPBearer()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_master_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> MasterToken:
    master_token_str = credentials.credentials
    master_token = db.query(MasterToken).filter(
        MasterToken.token == master_token_str,
        MasterToken.status == MasterTokenStatus.active,
    ).first()
    if not master_token:
        error_logger.log_error("Invalid or revoked master token", responsibility="vps_api")
        raise HTTPException(status_code=401, detail="Invalid or revoked master token")
    return master_token


def _resolve_token(credentials: HTTPAuthorizationCredentials, db: Session, now: datetime.datetime) -> Token:
    token = db.query(Token).filter(Token.token == credentials.credentials).first()
    if not token:
        raise HTTPException(status_code=401, detail="Невірний токен")
    if token.expires_at and token.expires_at < now:
        raise HTTPException(status_code=401, detail="Токен застарів")
    if token.max_uses and token.usage_count >= token.max_uses:
        raise HTTPException(status_code=401, detail="Перевищено ліміт використань")
    return token


def require_session_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> Token:
    now = datetime.datetime.utcnow()
    token = _resolve_token(credentials, db, now)
    token.usage_count = (token.usage_count or 0) + 1
    token.last_used_at = now
    db.commit()
    return token


def require_session_token_readonly(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> Token:
    """Те саме, що require_session_token, але БЕЗ запису usage_count/last_used_at.
    Уникає гонки запису (MySQL 1020) при паралельних читаннях (напр. кілька
    /1c/query з однієї сторінки одночасно). Ліміт max_uses тут не спрацьовує,
    бо usage_count не росте — свідомо, для чистих читань це не критично."""
    now = datetime.datetime.utcnow()
    return _resolve_token(credentials, db, now)