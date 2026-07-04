from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import get_db, require_master_token

router = APIRouter()


@router.post("/global_message_context/", response_model=schemas.GlobalMessageContextRead)
def create_global_message_context(
    item: schemas.GlobalMessageContextCreate,
    _master_token=Depends(require_master_token),
    db: Session = Depends(get_db),
):
    db_item = models.GlobalMessageContext(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.get("/global_message_context/", response_model=list[schemas.GlobalMessageContextRead])
def read_global_message_contexts(
    global_msg_id: int | None = None,
    _master_token=Depends(require_master_token),
    db: Session = Depends(get_db),
):
    query = db.query(models.GlobalMessageContext)
    if global_msg_id is not None:
        query = query.filter(models.GlobalMessageContext.global_msg_id == global_msg_id)
    return query.all()


@router.post("/global_message_telegram/", response_model=schemas.GlobalMessageTelegramRead)
def create_global_message_telegram(
    item: schemas.GlobalMessageTelegramCreate,
    _master_token=Depends(require_master_token),
    db: Session = Depends(get_db),
):
    db_item = models.GlobalMessageTelegram(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.get("/global_message_telegram/", response_model=list[schemas.GlobalMessageTelegramRead])
def read_global_message_telegrams(
    global_msg_id: int | None = None,
    _master_token=Depends(require_master_token),
    db: Session = Depends(get_db),
):
    query = db.query(models.GlobalMessageTelegram)
    if global_msg_id is not None:
        query = query.filter(models.GlobalMessageTelegram.global_msg_id == global_msg_id)
    return query.all()
