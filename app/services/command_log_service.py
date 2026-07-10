# command_log_service.py — журнал команд користувача (append-only, файл на команду).
# Кожен виклик log_command створює ОКРЕМИЙ .md-файл:
#   html_command_log/<user>/<YYYY-MM-DD>/<HHMMSS>_<desc>.md
# desc — короткий ASCII-ідентифікатор (для імені файлу), формулює викликач.
# user, time — ставить сервер (user з токена сесії, time — системний).
# Строга поведінка: порожній cmd або desc → 400 (нічого не пишемо).
# Тека html_command_log/ входить у бекап full_html (див. BACKUP_SETS).
#
# Зворотний зв'язок (back-reference): для КОЖНОГО файла зі списку files
# поруч із ним створюється/оновлюється сайдкар <ім'я_файла>.changes.md,
# куди додається посилання на щойно створений запис журналу (новіші зверху).
# Сайдкар містить ЛИШЕ посилання — переказ команди лишається в самому лозі
# (єдине джерело правди). Запис сайдкарів best-effort: помилка окремого
# сайдкара не зриває створення запису журналу, а повертається у відповіді.

import os
import re
from datetime import datetime

from fastapi import HTTPException

# Корінь проекту → тека журналу команд (на рівень із html/, queries1c/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "html_command_log")

# desc для імені файлу: лише ASCII-літери/цифри/дефіс/підкреслення
_DESC_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# Суфікс сайдкара з історією поруч зі зміненим файлом
_SIDECAR_SUFFIX = ".changes.md"
# Маркер-заголовок сайдкара (за ним впізнаємо «наш» файл при оновленні)
_SIDECAR_TITLE_PREFIX = "# Історія змін: "
_SIDECAR_SUBTITLE = (
    "_Автогенеровано command_log_service — посилання на журнал команд. "
    "Не редагувати вручну._"
)
# Максимальна довжина однорядкового тексту команди в сайдкарі
_SIDECAR_CMD_MAX = 160


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


def _cmd_oneline(cmd: str) -> str:
    """Команда одним рядком для сайдкара (стиснені пробіли, обрізка)."""
    line = " ".join(str(cmd or "").split())
    if len(line) > _SIDECAR_CMD_MAX:
        line = line[:_SIDECAR_CMD_MAX - 1].rstrip() + "…"
    return line


def _resolve_in_project(rel_path: str):
    """rel_path (repo-relative, з/без провідного слеша) → абсолютний шлях у межах
    PROJECT_ROOT. Повертає None, якщо шлях порожній або виходить за корінь."""
    rel = str(rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        return None
    abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, rel))
    root = os.path.normpath(PROJECT_ROOT)
    try:
        if os.path.commonpath([abs_path, root]) != root:
            return None
    except ValueError:
        # різні диски тощо
        return None
    return abs_path


def _write_backref(changed_abs: str, entry_line: str) -> str:
    """Створює/оновлює сайдкар поруч зі зміненим файлом; вписує entry_line зверху.
    Повертає repo-relative шлях сайдкара."""
    changed_name = os.path.basename(changed_abs)
    side_dir = os.path.dirname(changed_abs)
    side_path = os.path.join(side_dir, changed_name + _SIDECAR_SUFFIX)

    title = _SIDECAR_TITLE_PREFIX + changed_name

    if os.path.exists(side_path):
        with open(side_path, "r", encoding="utf-8") as fh:
            old = fh.read()
        lines = old.splitlines()
        if lines and lines[0].startswith(_SIDECAR_TITLE_PREFIX):
            # Наш сайдкар: заголовок = 3 рядки (title, subtitle, порожній),
            # нові записи — одразу під ними.
            head = lines[:3]
            rest = lines[3:]
            new_lines = head + [entry_line] + rest
            content = "\n".join(new_lines).rstrip("\n") + "\n"
        else:
            # Чужий вміст — нічого не руйнуємо, дописуємо в кінець.
            content = old.rstrip("\n") + "\n" + entry_line + "\n"
    else:
        content = f"{title}\n{_SIDECAR_SUBTITLE}\n\n{entry_line}\n"

    os.makedirs(side_dir, exist_ok=True)
    with open(side_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    return os.path.relpath(side_path, PROJECT_ROOT).replace("\\", "/")


def _write_backrefs(files: list, log_rel: str, dt: datetime,
                    user: str, cmd: str):
    """Для кожного файла зі списку дописує посилання на запис журналу.
    Повертає (written, errors): списки repo-relative шляхів / повідомлень."""
    written = []
    errors = []
    if not files:
        return written, errors

    log_name = os.path.basename(log_rel)
    log_link = "/" + log_rel.lstrip("/")
    stamp = dt.strftime("%Y-%m-%d %H:%M:%S")
    cmd_line = _cmd_oneline(cmd)
    entry_line = f"- {stamp} · {user} · {cmd_line} → [{log_name}]({log_link})"

    seen = set()
    for f in files:
        changed_abs = _resolve_in_project(f)
        if not changed_abs or changed_abs in seen:
            if changed_abs is None:
                errors.append(f"пропущено (шлях поза проектом або порожній): {f!r}")
            continue
        seen.add(changed_abs)
        try:
            written.append(_write_backref(changed_abs, entry_line))
        except OSError as e:
            errors.append(f"{f}: {e}")

    return written, errors


def log_command(cmd: str, desc: str, username: str = "",
                clar: str = "", why: str = "", files: list = None) -> dict:
    """Створює один файл журналу команди + сайдкари-посилання біля змінених файлів.
    Повертає {ok, file, sidecars, sidecar_errors}.
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

    files_list = files or []
    content = _build_content(time_iso, user, cmd_clean,
                             clar or "", why or "", files_list)

    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Помилка запису журналу: {e}")

    rel = os.path.relpath(abs_path, PROJECT_ROOT).replace("\\", "/")

    # Зворотні посилання біля змінених файлів (best-effort — не зриваємо запис журналу)
    sidecars, sidecar_errors = _write_backrefs(files_list, rel, now, user, cmd_clean)

    return {
        "ok": True,
        "file": rel,
        "sidecars": sidecars,
        "sidecar_errors": sidecar_errors,
    }