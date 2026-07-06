# backup_service.py — створення повних бекапів (zip-архів заданих тек).
# Псевдонім бекапу → перелік тек (реєстр у коді) → універсальний архіватор.
# Тека бекапів (BACKUP_DIR) — за межами проекту, з .env.
# М'яка поведінка: відсутня тека-джерело пропускається (не падаємо);
# невідомий псевдонім набору — 400.

import os
import zipfile
from datetime import datetime

from fastapi import HTTPException

from .. import query_loader

# Корінь проекту (там, де queries1c/, html/ тощо) — на рівень вище app/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

# Тека для архівів бекапів — за межами проекту, з .env
BACKUP_DIR = os.getenv("BACKUP_DIR", "")

# Скільки днів живуть тимчасові копії (чистяться при створенні повного знімка)
BACKUP_TEMP_DAYS = int(os.getenv("BACKUP_TEMP_DAYS", "7"))

# Реєстр наборів: псевдонім → перелік тек (відносно кореня проекту)
BACKUP_SETS = {
    "full_html": ["queries1c", "html"],
}


def _safe_segment(value: str, what: str) -> str:
    """Захист сегмента шляху від .., слешів, порожнечі."""
    v = str(value or "").strip()
    if not v or v in (".", ".."):
        raise HTTPException(status_code=400, detail=f"Недопустиме значення: {what}")
    if "/" in v or "\\" in v or "\x00" in v:
        raise HTTPException(status_code=400, detail=f"Недопустимі символи у: {what}")
    return v


def _archive_dirs(sources_abs: list, dest_zip: str) -> dict:
    """Універсальний архіватор: пакує список тек у один zip зі збереженням структури.
    Відсутні теки пропускає (м'яко). Повертає звіт {archived[], skipped[]}."""
    archived = []
    skipped = []

    os.makedirs(os.path.dirname(dest_zip), exist_ok=True)

    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for src in sources_abs:
            name = os.path.basename(src.rstrip(os.sep))
            if not os.path.isdir(src):
                skipped.append(name)
                continue
            # структура як є: у корені архіву тека зі своїм іменем
            for root, dirs, files in os.walk(src):
                for fname in files:
                    full = os.path.join(root, fname)
                    # шлях усередині архіву: <ім'я теки>/<відносний шлях>
                    rel = os.path.relpath(full, os.path.dirname(src))
                    zf.write(full, rel)
            archived.append(name)

    return {"archived": archived, "skipped": skipped}


def backup_temp_files(paths: list, username: str) -> dict:
    """Тимчасова копія файлів ПЕРЕД перезаписом (крок назад).
    paths: абсолютні шляхи файлів, які зараз існують і будуть перезаписані.
    Копіює кожен у <BACKUP_DIR>/temp/<username>/<таймстамп>_<ім'я_файлу>.
    Відсутні файли пропускає (новий запит — копіювати нічого).
    М'яка: жодних винятків назовні (бекап не має ламати основну операцію).
    Повертає {copied[]}."""
    if not BACKUP_DIR:
        return {"copied": []}  # без BACKUP_DIR тихо не бекапимо (не ламаємо save)

    import shutil

    user_safe = _safe_segment(username or "unknown", "username")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = os.path.join(BACKUP_DIR, "temp", user_safe)

    copied = []
    try:
        os.makedirs(temp_dir, exist_ok=True)
    except OSError:
        return {"copied": []}

    for src in paths:
        try:
            if not os.path.isfile(src):
                continue  # новий файл — старої версії нема
            base = os.path.basename(src)
            dst = os.path.join(temp_dir, f"{ts}_{base}")
            shutil.copy2(src, dst)
            copied.append(dst)
        except OSError:
            continue  # м'яко: помилка копії не валить основну операцію

    return {"copied": copied}


def cleanup_temp(days: int = None) -> dict:
    """Видаляє тимчасові копії, старші за `days` днів (з усіх тек користувачів у temp/).
    Викликається при створенні повного знімка. М'яка: помилки ігнорує.
    Повертає {removed}."""
    if not BACKUP_DIR:
        return {"removed": 0}
    import time as _time

    limit_days = BACKUP_TEMP_DAYS if days is None else days
    cutoff = _time.time() - limit_days * 86400
    temp_root = os.path.join(BACKUP_DIR, "temp")
    removed = 0

    if not os.path.isdir(temp_root):
        return {"removed": 0}

    for root, dirs, files in os.walk(temp_root):
        for fname in files:
            full = os.path.join(root, fname)
            try:
                if os.path.getmtime(full) < cutoff:
                    os.remove(full)
                    removed += 1
            except OSError:
                continue

    return {"removed": removed}


def create_backup(set_name: str, username: str) -> dict:
    """Створює zip-бекап набору тек за псевдонімом.
    set_name: ключ із BACKUP_SETS (напр. "full_html").
    username: автор (з токена сесії) — потрапляє в ім'я архіву.
    Файл: <BACKUP_DIR>/<set_name>/<таймстамп>_<username>.zip
    Повертає {ok, set_name, file, archived[], skipped[], warnings[]}."""

    if not BACKUP_DIR:
        raise HTTPException(status_code=500, detail="BACKUP_DIR не налаштовано у .env")

    # Невідомий псевдонім — помилка виклику (400)
    if set_name not in BACKUP_SETS:
        raise HTTPException(
            status_code=400,
            detail=f"Невідомий набір бекапу '{set_name}' (доступні: {', '.join(BACKUP_SETS)})",
        )

    set_safe = _safe_segment(set_name, "set_name")
    user_safe = _safe_segment(username or "unknown", "username")

    # Абсолютні шляхи джерел (від кореня проекту)
    sources_abs = [os.path.join(PROJECT_ROOT, rel) for rel in BACKUP_SETS[set_name]]

    # Призначення: <BACKUP_DIR>/<set_name>/<set_name>_<таймстамп>_<username>.zip
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_dir = os.path.join(BACKUP_DIR, set_safe)
    dest_zip = os.path.join(dest_dir, f"{set_safe}_{ts}_{user_safe}.zip")

    report = _archive_dirs(sources_abs, dest_zip)

    # Чистка прострочених тимчасових копій — у момент створення повного знімка
    cleanup = cleanup_temp()

    warnings = []
    if report["skipped"]:
        warnings.append("Пропущені (відсутні) теки: " + ", ".join(report["skipped"]))
    if not report["archived"]:
        warnings.append("Жодної теки не заархівовано — перевірте BACKUP_SETS і наявність тек")

    return {
        "ok": True,
        "set_name": set_name,
        "file": dest_zip,
        "archived": report["archived"],
        "skipped": report["skipped"],
        "temp_removed": cleanup["removed"],
        "warnings": warnings,
    }