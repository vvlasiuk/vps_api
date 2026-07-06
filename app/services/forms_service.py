# forms_service.py — робота з файлами фронтенду (тека html/).
# Читання: уся html/ (html/css/js) — контекст для генерації.
# Запис: ТІЛЬКИ в html/pages/ та html/menu/ (решта — lib/, components/, system/ — read-only).
# Перед перезаписом — тимчасова копія (backup_temp_files), автор з токена.

import os

from fastapi import HTTPException

# Корінь проекту → тека html/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
HTML_DIR = os.path.join(PROJECT_ROOT, "html")

# Підтеки html/, куди ДОЗВОЛЕНО писати
WRITE_DIRS = ["pages", "menu"]

# Типи файлів, які показує list (текстові, релевантні для генерації)
LIST_EXTENSIONS = (".html", ".css", ".js")


def _resolve(rel_path: str) -> str:
    """Абсолютний шлях усередині html/ з валідацією (без виходу за межі)."""
    rel = str(rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        raise HTTPException(status_code=400, detail="Порожній шлях")
    if ".." in rel.split("/"):
        raise HTTPException(status_code=400, detail="Недопустимий шлях (..)")
    abs_path = os.path.abspath(os.path.join(HTML_DIR, rel))
    # підсумковий шлях має лишатися всередині html/ (з роздільником, щоб html_evil не пройшов)
    root = os.path.abspath(HTML_DIR)
    if abs_path != root and not abs_path.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="Шлях виходить за межі html/")
    return abs_path


def _is_writable(rel_path: str) -> bool:
    """Чи дозволено писати за цим шляхом (перша частина шляху — у WRITE_DIRS)."""
    rel = str(rel_path or "").strip().replace("\\", "/").lstrip("/")
    parts = rel.split("/")
    return len(parts) > 0 and parts[0] in WRITE_DIRS


def list_forms() -> dict:
    """Рекурсивний перелік файлів html/ (тільки .html/.css/.js).
    Повертає {total, files:[{path, ext, writable, size}]}."""
    if not os.path.isdir(HTML_DIR):
        raise HTTPException(status_code=500, detail=f"Тека html/ не знайдена: {HTML_DIR}")

    files = []
    for root, dirs, names in os.walk(HTML_DIR):
        for name in names:
            if not name.lower().endswith(LIST_EXTENSIONS):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, HTML_DIR).replace("\\", "/")
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            files.append({
                "path": rel,
                "ext": os.path.splitext(name)[1].lower(),
                "writable": _is_writable(rel),
                "size": size,
            })
    files.sort(key=lambda f: f["path"])
    return {"total": len(files), "files": files}


def read_form(rel_path: str) -> dict:
    """Читає вміст файлу з html/ (будь-який дозволений шлях у межах html/).
    Повертає {path, content, writable}."""
    abs_path = _resolve(rel_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail=f"Файл не знайдено: {rel_path}")
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Помилка читання: {e}")
    rel = os.path.relpath(abs_path, HTML_DIR).replace("\\", "/")
    return {"path": rel, "content": content, "writable": _is_writable(rel)}


def write_form(rel_path: str, content: str, username: str = "") -> dict:
    """Записує/перезаписує файл ТІЛЬКИ в дозволених теках (pages/, menu/).
    Перед перезаписом наявного — тимчасова копія. Створює підтеки за потреби.
    Повертає {ok, path}."""
    rel = str(rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not _is_writable(rel):
        raise HTTPException(
            status_code=403,
            detail=f"Запис дозволено лише в {', '.join(WRITE_DIRS)}/ (шлях: {rel})",
        )

    abs_path = _resolve(rel)

    if content is None:
        raise HTTPException(status_code=400, detail="Порожній вміст (content)")

    # Тимчасова копія перед перезаписом (якщо файл існує)
    from .backup_service import backup_temp_files
    backup_temp_files([abs_path], username)

    try:
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Помилка запису: {e}")

    return {"ok": True, "path": rel}