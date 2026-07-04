import datetime
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_master_token
from ..models import Context
from ..schemas import ContextCreate, ContextResponse, ContextUpdate

router = APIRouter()


@router.post("/context", response_model=ContextResponse)
def create_context(
    req: ContextCreate,
    _master_token=Depends(require_master_token),
    db: Session = Depends(get_db),
):
    now = datetime.datetime.utcnow()
    ctx = Context(
        object_id=req.object_id,
        context_data=json.dumps(req.context_data),
        created_at=now,
        updated_at=now,
        end_at=req.end_at,
        closed=False,
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
        end_at=ctx.end_at,
        closed=ctx.closed,
    )


@router.get("/context/{object_id}", response_model=ContextResponse)
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
        closed=ctx.closed,
    )


@router.get("/context_by_id/{id}", response_model=ContextResponse)
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
        end_at=getattr(ctx, "end_at", None),
    )


@router.put("/context/{object_id}", response_model=ContextResponse)
def update_context(object_id: str, req: ContextUpdate, db: Session = Depends(get_db)):
    ctx = db.query(Context).filter(Context.object_id == object_id).first()
    if not ctx:
        raise HTTPException(status_code=404, detail="Context not found")

    ctx.context_data = json.dumps(req.context_data)
    ctx.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(ctx)

    return ContextResponse(
        id=ctx.id,
        object_id=ctx.object_id,
        context_data=json.loads(ctx.context_data),
        created_at=ctx.created_at,
        updated_at=ctx.updated_at,
        closed=ctx.closed,
    )


@router.post("/context/{id}/close")
def close_context(
    id: int,
    _master_token=Depends(require_master_token),
    db: Session = Depends(get_db),
):
    ctx = db.query(Context).filter(Context.id == id).first()
    if not ctx:
        raise HTTPException(status_code=404, detail="Context not found")

    ctx.closed = True
    ctx.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(ctx)
    return {"status": "closed", "id": ctx.id}
