# forms_service.py — робота з файлами фронтенду (тека html/).
# Читання: уся html/ (html/css/js) — контекст для генерації.
# Запис: ТІЛЬКИ в html/pages/ та html/menu/ (решта — lib/, components/, system/ — read-only).
# Перед перезаписом — тимчасова копія (backup_temp_files), автор з токена.
#
# При кожному записі .html-файлу сервер сам домальовує (idempotent, за анкорами):
#   1) версію (meta в <head> + футер перед </body>) — завжди;
#   2) user-chip + кнопку "Вийти" в <header class="page-head"> — якщо такий є;
#   3) підключення lib/version_check.js — якщо ще не підключено.
# Контент, який передає користувач/Claude, цим не чіпається за змістом —
# лише додаються/оновлюються ці три службові блоки.

import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

# Корінь проекту → тека html/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
HTML_DIR = os.path.join(PROJECT_ROOT, "html")

# Підтеки html/, куди ДОЗВОЛЕНО писати
WRITE_DIRS = ["pages", "menu"]

# Типи файлів, які показує list (текстові, релевантні для генерації)
LIST_EXTENSIONS = (".html", ".css", ".js")

KYIV_TZ = ZoneInfo("Europe/Kyiv")

# ── Анкори для ідемпотентної вставки/заміни службових блоків ──
_VERSION_META_START = "<!-- APP_VERSION_START -->"
_VERSION_META_END = "<!-- APP_VERSION_END -->"
_VERSION_FOOTER_START = "<!-- APP_VERSION_FOOTER_START -->"
_VERSION_FOOTER_END = "<!-- APP_VERSION_FOOTER_END -->"
_USER_CHIP_START = "<!-- USER_CHIP_START -->"
_USER_CHIP_END = "<!-- USER_CHIP_END -->"
_VERSION_SCRIPT_START = "<!-- VERSION_CHECK_SCRIPT_START -->"
_VERSION_SCRIPT_END = "<!-- VERSION_CHECK_SCRIPT_END -->"

_VERSION_META_RE = re.compile(r'<meta\s+name="app-version"\s+content="([^"]*)"', re.IGNORECASE)
_PAGE_HEAD_OPEN_RE = re.compile(r'<header[^>]*class="[^"]*page-head[^"]*"[^>]*>')


def _resolve(rel_path: str) -> str:
    """Абсолютний шлях усередині html/ з валідацією (без виходу за межі)."""
    rel = str(rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        raise HTTPException(status_code=400, detail="Порожній шлях")
    if ".." in rel.split("/"):
        raise HTTPException(status_code=400, detail="Недопустимий шлях (..)")
    abs_path = os.path.abspath(os.path.join(HTML_DIR, rel))
    root = os.path.abspath(HTML_DIR)
    if abs_path != root and not abs_path.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="Шлях виходить за межі html/")
    return abs_path


def _is_writable(rel_path: str) -> bool:
    """Чи дозволено писати за цим шляхом (перша частина шляху — у WRITE_DIRS)."""
    rel = str(rel_path or "").strip().replace("\\", "/").lstrip("/")
    parts = rel.split("/")
    return len(parts) > 0 and parts[0] in WRITE_DIRS


# ═══ СЛУЖБОВІ БЛОКИ (версія, user-chip, підключення скрипта) ═══

def _replace_or_insert(content: str, start: str, end: str, block: str, before_marker: str) -> str:
    """Замінити вміст між анкорами (якщо анкори вже є) або вставити block
    перед першим входженням before_marker (якщо анкорів ще немає).
    Якщо before_marker не знайдено — content лишається без змін (нічого не ламаємо)."""
    full = f"{start}{block}{end}"
    pattern = re.escape(start) + r".*?" + re.escape(end)
    if re.search(pattern, content, flags=re.DOTALL):
        return re.sub(pattern, lambda m: full, content, count=1, flags=re.DOTALL)
    idx = content.find(before_marker)
    if idx == -1:
        return content
    return content[:idx] + full + "\n" + content[idx:]


def _version_blocks() -> tuple[str, str]:
    now = datetime.now(KYIV_TZ)
    machine = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    machine = machine[:-2] + ":" + machine[-2:]  # +0300 → +03:00
    human = now.strftime("%d.%m.%Y %H:%M")
    meta = f'\n<meta name="app-version" content="{machine}">\n'
    footer = (
        '\n<div id="app-version-footer" style="text-align:center;padding:10px 0;'
        'font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:#9ca3af;">'
        f'Версія: {human}</div>\n'
    )
    return meta, footer


_USER_CHIP_BLOCK = '''
<div id="app-user-chip" style="display:flex;align-items:center;gap:8px;margin-left:auto;">
  <div style="display:flex;align-items:center;gap:6px;padding:4px 10px;border-radius:20px;background:#f0f2f5;border:1px solid #e5e7eb;">
    <div id="app-user-avatar" style="width:22px;height:22px;border-radius:50%;background:#2563eb;color:#fff;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;flex-shrink:0;">?</div>
    <div id="app-user-name" style="font-size:12px;font-weight:500;color:#111827;">—</div>
  </div>
  <button onclick="AUTH.logout()" style="padding:5px 12px;border-radius:7px;background:none;border:1px solid #e5e7eb;font-family:inherit;font-size:12px;color:#6b7280;cursor:pointer;">Вийти</button>
</div>
<script>
(function () {
    var n = (window.AUTH && AUTH.username) || "—";
    var nameEl = document.getElementById("app-user-name");
    var avEl = document.getElementById("app-user-avatar");
    if (nameEl) nameEl.textContent = n;
    if (avEl) avEl.textContent = n.charAt(0).toUpperCase();
})();
</script>
'''

_VERSION_SCRIPT_BLOCK = '\n<script src="/html/lib/version_check.js"></script>\n'


def _inject_version(content: str) -> str:
    meta, footer = _version_blocks()
    content = _replace_or_insert(content, _VERSION_META_START, _VERSION_META_END, meta, "</head>")
    content = _replace_or_insert(content, _VERSION_FOOTER_START, _VERSION_FOOTER_END, footer, "</body>")
    return content


def _inject_user_chip(content: str) -> str:
    head_match = _PAGE_HEAD_OPEN_RE.search(content)
    if not head_match:
        return content  # немає .page-head на цій сторінці — не чіпаємо
    close_idx = content.find("</header>", head_match.end())
    if close_idx == -1:
        return content
    # Той самий анкор-патерн, але точку вставки (якщо анкорів ще нема)
    # обчислюємо саме як позицію ЦЬОГО </header>, а не будь-якого маркера в тексті.
    full = f"{_USER_CHIP_START}{_USER_CHIP_BLOCK}{_USER_CHIP_END}"
    pattern = re.escape(_USER_CHIP_START) + r".*?" + re.escape(_USER_CHIP_END)
    if re.search(pattern, content, flags=re.DOTALL):
        return re.sub(pattern, lambda m: full, content, count=1, flags=re.DOTALL)
    return content[:close_idx] + full + "\n" + content[close_idx:]


def _inject_version_script(content: str) -> str:
    return _replace_or_insert(
        content, _VERSION_SCRIPT_START, _VERSION_SCRIPT_END, _VERSION_SCRIPT_BLOCK, "</head>"
    )


def _apply_service_blocks(content: str) -> str:
    """Застосовує всі три службові блоки поверх контенту користувача."""
    content = _inject_version(content)
    content = _inject_user_chip(content)
    content = _inject_version_script(content)
    return content


# ═══ ПУБЛІЧНІ ФУНКЦІЇ ═══

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


def get_form_version(rel_path: str) -> dict:
    """Легкий ендпойнт: лише версія сторінки (з <meta name="app-version">),
    без передачі всього HTML. Повертає {path, version} (version=None, якщо міток ще немає)."""
    abs_path = _resolve(rel_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail=f"Файл не знайдено: {rel_path}")
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Помилка читання: {e}")
    m = _VERSION_META_RE.search(content)
    rel = os.path.relpath(abs_path, HTML_DIR).replace("\\", "/")
    return {"path": rel, "version": m.group(1) if m else None}


def write_form(rel_path: str, content: str, username: str = "") -> dict:
    """Записує/перезаписує файл ТІЛЬКИ в дозволених теках (pages/, menu/).
    Для .html-файлів перед записом домальовує службові блоки (версія,
    user-chip, підключення version_check.js) — див. _apply_service_blocks.
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

    if rel.lower().endswith(".html"):
        content = _apply_service_blocks(content)

    from .backup_service import backup_temp_files
    backup_temp_files([abs_path], username)

    try:
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Помилка запису: {e}")

    return {"ok": True, "path": rel}