# command_log_service.py — журнал команд користувача (append-only, файл на команду).
# Кожен виклик log_command створює ОКРЕМИЙ .md-файл:
#   html_command_log/<user>/<YYYY-MM-DD>/<HHMMSS>_<desc>.md
# desc — короткий ASCII-ідентифікатор (для імені файлу), формулює викликач.
# user, time — ставить сервер (user з токена сесії, time — системний).
# Строга поведінка: порожній cmd або desc → 400 (нічого не пишемо).
# Тека html_command_log/ входить у бекап full_html (див. BACKUP_SETS).

import os
import re
from datetime import datetime

from fastapi import HTTPException

# Корінь проекту → тека журналу команд (на рівень із html/, queries1c/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "html_command_log")

# desc для імені файлу: лише ASCII-літери/цифри/дефіс/підкреслення
_DESC_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _safe_user(value: str) -> str:
    """Сегмент теки користувача — без слешів, .., порожнечі."""
    v = str(value or "").strip()
    if not v or v in (".", "..") or "/" in v or "\\" in v or "\x00" in v:
        v = "unknown"
    return v


def _md_line(value: str) -> str:
    """Значення для тіла нотатки; порожнє → тире."""
    v = str(value or "").strip()
    return v if v else "—"


def _build_content(time_iso: str, user: str, cmd: str,
                   clar: str, why: str, files: list) -> str:
    """Формує вміст .md: YAML-frontmatter (службове) + тіло (клікабельні посилання)."""
    fm = [
        "---",
        f"time: {time_iso}",
        f"user: {user}",
        # cmd у лапках — може містити двокрапки/спецсимволи
        f"cmd: {_yaml_quote(cmd)}",
        "---",
        "",
    ]

    body = [
        "**Команда**",
        cmd.strip(),
        "",
        "**Уточнення**",
        _md_line(clar),
        "",
        "**Чому**",
        _md_line(why),
        "",
        "**Зачеплені файли**",
    ]

    if files:
        for f in files:
            rel = str(f or "").strip().replace("\\", "/")
            if not rel:
                continue
            link = rel if rel.startswith("/") else "/" + rel
            name = os.path.basename(rel)
            body.append(f"- [{name}]({link})")
    else:
        body.append("—")

    body.append("")
    return "\n".join(fm) + "\n".join(body) + "\n"


def _yaml_quote(s: str) -> str:
    """Безпечне однорядкове YAML-значення в подвійних лапках."""
    s = str(s or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()
    return f'"{s}"'


def log_command(cmd: str, desc: str, username: str = "",
                clar: str = "", why: str = "", files: list = None) -> dict:
    """Створює один файл журналу команди. Повертає {ok, file}.
    400 — якщо cmd або desc порожні / desc не ASCII-ідентифікатор."""
    cmd_clean = str(cmd or "").strip()
    desc_clean = str(desc or "").strip()

    if not cmd_clean:
        raise HTTPException(status_code=400, detail="Порожня команда (cmd)")
    if not desc_clean:
        raise HTTPException(status_code=400, detail="Порожній опис для імені файлу (desc)")
    if not _DESC_RE.match(desc_clean):
        raise HTTPException(
            status_code=400,
            detail="desc має бути ASCII: літери, цифри, дефіс, підкреслення (без пробілів/кирилиці)",
        )

    user = _safe_user(username)
    now = datetime.now()
    date_dir = now.strftime("%Y-%m-%d")
    hms = now.strftime("%H%M%S")
    time_iso = now.strftime("%Y-%m-%dT%H:%M:%S")

    target_dir = os.path.join(LOG_DIR, user, date_dir)
    base_name = f"{hms}_{desc_clean}.md"
    abs_path = os.path.join(target_dir, base_name)

    # Колізія в ту саму секунду — суфікс _2, _3, ...
    if os.path.exists(abs_path):
        i = 2
        while True:
            alt = os.path.join(target_dir, f"{hms}_{desc_clean}_{i}.md")
            if not os.path.exists(alt):
                abs_path = alt
                break
            i += 1

    content = _build_content(time_iso, user, cmd_clean,
                             clar or "", why or "", files or [])

    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Помилка запису журналу: {e}")

    rel = os.path.relpath(abs_path, PROJECT_ROOT).replace("\\", "/")
    return {"ok": True, "file": rel}