# photos_service.py — фото документів і довідників на диску.
# Структура: {ONEC_PHOTOS_DIR}/{Документи|Довідники}/{назва_обʼєкта}/{ref}/NNNN.ext
#   object_type — повний тип посилання 1С ("Документ.X" або "Справочник.Y");
#   бекенд сам ріже його на теку виду (Документи/Довідники) + назву обʼєкта.
#   ref — guid обʼєкта.
# Захист: whitelist префіксів, валідація назви/ref/name (без traversal),
# ліміт розміру/кількості, перевірка, що вміст справді зображення (магічні байти).

import os
import re

from fastapi import HTTPException, UploadFile

from ..runtime import ONEC_PHOTOS_DIR

MAX_SIZE  = 10 * 1024 * 1024   # 10 МБ на файл
MAX_COUNT = 30                  # максимум фото на обʼєкт

# Префікс типу 1С → тека верхнього рівня. Whitelist: інше не пускаємо.
_KIND_MAP = {
    "Документ":    "Документи",
    "Справочник":  "Довідники",
}

# guid 1С: 8-4-4-4-12 hex (з дефісами). Нічого іншого в шлях не пускаємо.
_GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# Назва обʼєкта: літери (вкл. кирилицю), цифри, підкреслення. Без роздільників/крапок.
_NAME_OBJ_RE = re.compile(r"^\w+$", re.UNICODE)
# Імʼя файлу фото, яке ми самі створюємо: NNNN.ext
_FILE_RE = re.compile(r"^\d{4}\.(jpg|png)$")

_MEDIA = {"jpg": "image/jpeg", "png": "image/png"}


def _sniff_ext(head: bytes) -> str:
    """Розширення за магічними байтами (довіряємо вмісту, не імені)."""
    if head[:3] == b"\xff\xd8\xff":
        return "jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return ""


def _split_type(object_type: str):
    """Повний тип 1С → (тека_виду, назва_обʼєкта). Напр.:
       "Документ.ПрийомНаСервіс..._ПСТ" → ("Документи", "ПрийомНаСервіс..._ПСТ")
       "Справочник.М_ИзделияДляСервиса" → ("Довідники", "М_ИзделияДляСервиса")"""
    s = str(object_type or "").strip()
    if "." not in s:
        raise HTTPException(status_code=400, detail="Недопустимий тип обʼєкта")
    prefix, name = s.split(".", 1)
    kind = _KIND_MAP.get(prefix.strip())
    if not kind:
        raise HTTPException(status_code=400, detail="Тип обʼєкта не підтримується")
    name = name.strip()
    if not _NAME_OBJ_RE.match(name):
        raise HTTPException(status_code=400, detail="Недопустима назва обʼєкта")
    return kind, name


def _obj_dir(object_type: str, ref: str, create: bool = False) -> str:
    """Абсолютний шлях {ONEC_PHOTOS_DIR}/{вид}/{назва}/{ref} з валідацією (без виходу за межі)."""
    if not ONEC_PHOTOS_DIR:
        raise HTTPException(status_code=500, detail="ONEC_PHOTOS_DIR не налаштовано")

    kind, name = _split_type(object_type)
    ref = str(ref or "").strip().lower()
    if not _GUID_RE.match(ref):
        raise HTTPException(status_code=400, detail="Недопустимий ref обʼєкта")

    root = os.path.abspath(ONEC_PHOTOS_DIR)
    path = os.path.abspath(os.path.join(root, kind, name, ref))
    if path != root and not path.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="Шлях виходить за межі сховища фото")

    if create:
        os.makedirs(path, exist_ok=True)
    return path


def _existing(path: str) -> list[str]:
    """Наявні файли фото в папці (відсортовані за іменем)."""
    if not os.path.isdir(path):
        return []
    names = [n for n in os.listdir(path) if _FILE_RE.match(n)]
    names.sort()
    return names


def _next_index(names: list[str]) -> int:
    """Наступний порядковий номер (max+1), щоб не було колізій після видалень."""
    mx = 0
    for n in names:
        try:
            mx = max(mx, int(n[:4]))
        except ValueError:
            pass
    return mx + 1


def save_photos(object_type: str, ref: str, files: list[UploadFile]) -> dict:
    """Заливка фото у папку обʼєкта. Повертає {ok, saved:[{name,size}], total}."""
    if not files:
        raise HTTPException(status_code=400, detail="Немає файлів")

    path = _obj_dir(object_type, ref, create=True)
    names = _existing(path)
    if len(names) + len(files) > MAX_COUNT:
        raise HTTPException(status_code=400, detail=f"Забагато фото (максимум {MAX_COUNT})")

    idx = _next_index(names)
    saved = []
    for f in files:
        data = f.file.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"Порожній файл: {f.filename}")
        if len(data) > MAX_SIZE:
            raise HTTPException(status_code=400, detail=f"Файл більший за 10 МБ: {f.filename}")
        ext = _sniff_ext(data[:16])
        if not ext:
            raise HTTPException(status_code=400, detail=f"Файл не є JPG/PNG: {f.filename}")

        name = f"{idx:04d}.{ext}"
        try:
            with open(os.path.join(path, name), "wb") as out:
                out.write(data)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Помилка запису: {e}")
        saved.append({"name": name, "size": len(data)})
        idx += 1

    return {"ok": True, "saved": saved, "total": len(names) + len(saved)}


def list_photos(object_type: str, ref: str) -> dict:
    """Список фото обʼєкта. Повертає {total, photos:[{name,size}]}."""
    path = _obj_dir(object_type, ref)
    photos = []
    for n in _existing(path):
        try:
            size = os.path.getsize(os.path.join(path, n))
        except OSError:
            size = 0
        photos.append({"name": n, "size": size})
    return {"total": len(photos), "photos": photos}


def read_photo(object_type: str, ref: str, name: str):
    """Абсолютний шлях + media_type для віддачі одного фото."""
    name = str(name or "").strip()
    if not _FILE_RE.match(name):
        raise HTTPException(status_code=400, detail="Недопустиме імʼя файлу")
    path = _obj_dir(object_type, ref)
    full = os.path.join(path, name)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="Фото не знайдено")
    ext = name.rsplit(".", 1)[-1].lower()
    return full, _MEDIA.get(ext, "application/octet-stream")


def delete_photo(object_type: str, ref: str, name: str) -> dict:
    """Видалення одного фото обʼєкта."""
    name = str(name or "").strip()
    if not _FILE_RE.match(name):
        raise HTTPException(status_code=400, detail="Недопустиме імʼя файлу")
    path = _obj_dir(object_type, ref)
    full = os.path.join(path, name)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="Фото не знайдено")
    try:
        os.remove(full)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Помилка видалення: {e}")
    return {"ok": True}