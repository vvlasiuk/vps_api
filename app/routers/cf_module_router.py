"""
Роутер доступу до контексту конфігурації 1С (артефакт cf_module).

Віддає моделі/MCP компактні зрізи маніфесту: де оголошено символ, зміст
модуля, кістяк (компакт/повний), тіло процедури. Кожен ендпойнт — один
вузький SELECT через ManifestReader; нічого не парситься в рантаймі.

Автентифікація — require_session_token, як в інших читальних ендпойнтах.
Шлях до маніфесту береться з runtime.ONEC_CF_MODULE_MANIFEST.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_session_token
from ..runtime import ONEC_CF_MODULE_MANIFEST
from ..services.cf_module_reader import ManifestReader, ManifestNotConfigured

router = APIRouter(prefix="/cf_module", tags=["cf_module"])

# Читач тримає лише шлях; з'єднання відкривається на кожен запит (дешево).
_reader = ManifestReader(ONEC_CF_MODULE_MANIFEST)


def _guard():
    if not _reader.available():
        raise HTTPException(
            status_code=503,
            detail="Маніфест cf_module недоступний (перевірте ONEC_CF_MODULE_MANIFEST)")


@router.get("/meta")
def ctx_meta(_session_token=Depends(require_session_token)):
    """Свіжість і лічильники артефакту."""
    _guard()
    return _reader.meta()


@router.get("/where/{name}")
def ctx_where(
    name: str,
    export_only: bool = Query(True, description="шукати лише серед експортних"),
    limit: int = Query(50, ge=1, le=500),
    _session_token=Depends(require_session_token),
):
    """Де оголошено символ (процедуру/функцію)."""
    _guard()
    return {"name": name, "export_only": export_only,
            "results": _reader.where_defined(name, export_only, limit)}


@router.get("/module/toc")
def ctx_module_toc(
    path: str = Query(..., description="шлях модуля у дереві вивантаження"),
    _session_token=Depends(require_session_token),
):
    """Зміст модуля: роль + перелік процедур (найдешевший зріз)."""
    _guard()
    toc = _reader.module_toc(path)
    if toc is None:
        raise HTTPException(status_code=404, detail="Модуль не знайдено")
    return toc


@router.get("/module/skeleton")
def ctx_module_skeleton(
    path: str = Query(...),
    level: str = Query("compact", pattern="^(compact|full)$"),
    _session_token=Depends(require_session_token),
):
    """Кістяк модуля: level=compact (сигнатури) або full (з доккоментарями)."""
    _guard()
    text = _reader.skeleton(path, level)
    if text is None:
        raise HTTPException(status_code=404, detail="Модуль не знайдено")
    return {"module": path, "level": level, "text": text}


@router.get("/body")
def ctx_body(
    module: str = Query(...),
    name: str = Query(...),
    _session_token=Depends(require_session_token),
):
    """Текст цілої процедури за модулем та іменем."""
    _guard()
    text = _reader.body(module, name)
    if text is None:
        raise HTTPException(status_code=404, detail="Процедуру не знайдено")
    return {"module": module, "name": name, "text": text}


@router.get("/search")
def ctx_search(
    prefix: str = Query(..., min_length=2),
    export_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=500),
    _session_token=Depends(require_session_token),
):
    """Пошук символів за префіксом імені."""
    _guard()
    return {"prefix": prefix, "results": _reader.search_symbols(
        prefix, export_only, limit)}


@router.get("/modules/top")
def ctx_top_modules(
    limit: int = Query(20, ge=1, le=200),
    _session_token=Depends(require_session_token),
):
    """Найбільші модулі за кількістю процедур (орієнтація по god-модулях)."""
    _guard()
    return {"results": _reader.top_modules(limit)}

@router.get("/object")
def ctx_object_modules(
    type: str = Query(..., description="тип об'єкта 1С, напр. Справочник"),
    name: str = Query(..., description="ім'я об'єкта, напр. Контрагенты"),
    _session_token=Depends(require_session_token),
):
    """Усі модулі об'єкта (модуль об'єкта, менеджера, форм) з ролями."""
    _guard()
    mods = _reader.object_modules_by_type(type, name)
    if mods is None:
        raise HTTPException(
            status_code=400, detail=f"Невідомий тип об'єкта: {type}")
    return {"type": type, "name": name, "modules": mods}

@router.get("/find")
def ctx_find(
    query: str = Query(..., min_length=2, description="ім'я/текст для пошуку використань"),
    match: str = Query("word", pattern="^(word|contains|prefix)$",
                       description="word=по межах слова, contains=будь-де, prefix=з початку"),
    type: str | None = Query(None, description="тип об'єкта 1С для звуження, напр. Справочник"),
    name: str | None = Query(None, description="ім'я об'єкта (разом із type)"),
    path_prefix: str | None = Query(None, description="префікс module_path (альтернатива type+name)"),
    role: str | None = Query(None, description="фільтр за роллю модуля"),
    max_modules: int = Query(200, ge=1, le=2000),
    max_per_module: int = Query(20, ge=1, le=500),
    context_lines: int = Query(0, ge=0, le=5, description="± рядків контексту навколо збігу"),
    _session_token=Depends(require_session_token),
):
    """Знайти всі використання імені/тексту в коді (тіла процедур + рівень модуля)."""
    _guard()
    try:
        return _reader.find_usages(
            query, match=match, type_1c=type, type_name=name,
            path_prefix=path_prefix, role=role,
            max_modules=max_modules, max_per_module=max_per_module,
            context_lines=context_lines)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))