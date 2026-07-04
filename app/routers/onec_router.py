import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import query_loader
from ..dependencies import get_db, require_session_token
from ..models import User
from ..runtime import (
    ONEC_METADATA_DESCRIBE_URL,
    ONEC_METADATA_OBJECTS_URL,
    ONEC_QUERY_URL,
    ONEC_SAVE_DOC_URL,
    ONEC_TOKEN,
    error_logger,
)
from ..schemas import (
    GenerateQueryRequest,
    MetadataDescribeRequest,
    MetadataQueriesRequest,
    OneCQueryRequest,
    OneCQueryResponse,
    QueryGetRequest,
    SaveDocRequest,
    SaveDocResponse,
    SaveQueryRequest,
)
from ..services.onec_service import call_onec_read, call_onec_save
from ..services.query_writer import generate_query, read_query, save_query

router = APIRouter()


@router.post("/1c/query", response_model=OneCQueryResponse)
def onec_query(
    req: OneCQueryRequest,
    _session_token=Depends(require_session_token),
):
    cfg = query_loader.get_query(req.query)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Запит '{req.query}' не знайдено")

    inner_query = cfg["query"]
    fields_sql = ", ".join(req.fields) if req.fields else "*"

    wrapped = f"ВЫБРАТЬ {fields_sql}\nИЗ (\n{inner_query}\n) КАК Вложенный"

    if req.filters:
        wrapped += f"\nГДЕ {req.filters}"

    if req.order:
        wrapped += f"\nУПОРЯДОЧИТЬ ПО {req.order}"

    onec_params = {}
    if req.params:
        for key, p in req.params.items():
            onec_params[key] = {"type": p.type, "value": p.value}

    payload = {
        "token": ONEC_TOKEN,
        "query": wrapped,
        "params": onec_params,
        "offset": req.offset,
        "limit": req.limit,
    }

    try:
        t0 = time.time()
        response = httpx.post(ONEC_QUERY_URL, json=payload, timeout=30)
        print(f"[1c call] query {ONEC_QUERY_URL} - {int((time.time() - t0) * 1000)} ms")
    except httpx.RequestError as exc:
        error_logger.log_error(f"1С недоступний: {exc}", responsibility="vps_api")
        raise HTTPException(status_code=503, detail="1С сервіс недоступний")

    if response.status_code == 401:
        raise HTTPException(status_code=502, detail="Помилка авторизації до 1С")

    if response.status_code != 200:
        try:
            data = response.json()
        except Exception:
            data = {"error": f"1С повернула HTTP {response.status_code}"}
        error_logger.log_error(f"1С помилка: {data}", responsibility="vps_api")
        raise HTTPException(status_code=502, detail=data.get("error", "Помилка 1С"))

    return response.json()


@router.post("/1c/save_doc", response_model=SaveDocResponse)
def onec_save_doc(
    req: SaveDocRequest,
    token=Depends(require_session_token),
    db: Session = Depends(get_db),
):
    onec_fields = {}
    if req.fields:
        for key, p in req.fields.items():
            onec_fields[key] = {"type": p.type, "value": p.value}

    username = None
    if token.user_id:
        user = db.query(User).filter(User.id == token.user_id).first()
        if user:
            username = user.username
    if username:
        onec_fields["Ответственный"] = {"type": "string", "value": username}

    payload = {
        "document": req.document,
        "ref": req.ref,
        "version": req.version,
        "date": req.date,
        "action": req.action,
        "fields": onec_fields,
    }

    if req.fields_search is not None:
        payload["fields_search"] = req.fields_search

    return call_onec_save(ONEC_SAVE_DOC_URL, payload)


@router.post("/1c/metadata_objects")
def onec_metadata_objects(
    _session_token=Depends(require_session_token),
):
    return call_onec_read(ONEC_METADATA_OBJECTS_URL, {}, label="metadata_objects")


@router.post("/1c/metadata_describe")
def onec_metadata_describe(
    req: MetadataDescribeRequest,
    _session_token=Depends(require_session_token),
):
    payload = {"type": req.type, "name": req.name}
    return call_onec_read(ONEC_METADATA_DESCRIBE_URL, payload, label="metadata_describe")


@router.post("/metadata/queries")
def metadata_queries(
    req: MetadataQueriesRequest,
    _session_token=Depends(require_session_token),
):
    """Наявні запити (.sel/.json), прив'язані до об'єкта 1С."""
    items = query_loader.list_queries_for_object(req.object_type, req.object_name)
    return {"total": len(items), "queries": items}


@router.post("/metadata/save_query")
def metadata_save_query(
    req: SaveQueryRequest,
    _session_token=Depends(require_session_token),
):
    """Запис .sel/.json запиту + гарячий перечит loader."""
    return save_query(req.file_name, req.sel, req.meta)


@router.post("/metadata/query_get")
def metadata_query_get(
    req: QueryGetRequest,
    _session_token=Depends(require_session_token),
):
    """Сирий вміст .sel/.json одного запиту (для редагування)."""
    return read_query(req.query_name)


@router.post("/metadata/generate_query")
def metadata_generate_query(
    req: GenerateQueryRequest,
    _session_token=Depends(require_session_token),
):
    """Чернетка запиту з describe об'єкта (без запису). task заданий → через AI, інакше механіка.
    Якщо передано current_sel/current_meta — AI редагує наявний запит, а не генерує з нуля."""
    return generate_query(
        req.object_type, req.object_name, req.task,
        current_sel=req.current_sel, current_meta=req.current_meta,
    )