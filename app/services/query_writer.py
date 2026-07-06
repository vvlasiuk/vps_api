# query_writer.py — запис конфігів запитів (.sel + .json) на диск + гарячий перечит loader.
# НЕ ходить у 1С (це про файли). Викликається з ендпоінта save_query.
#
# Контракт входу (див. schemas.SaveQueryRequest):
#   file_name : ім'я файлу без розширення; "" → береться з json.query_name
#   sel       : текст запиту (.sel), непорожній
#   json      : вміст .json — ДЖЕРЕЛО ПРАВДИ (query_name, object_type, object_name, info, fields...)
#
# Тека визначається за object_type: Справочник → catalogs, Документ → documents.
# Файли пишуться у queries1c/<тека>/<object_name>/<file_name>.sel + .json
# Після запису — повний load_queries() (перечит усієї теки в пам'ять).

import os
import json as json_lib

from fastapi import HTTPException

from .. import query_loader
from ..runtime import ONEC_METADATA_DESCRIBE_URL, ONEC_SOURCE_NAME
from .onec_service import call_onec_read

# Тека з конфігами запитів (та сама, що сканує query_loader)
QUERIES_DIR = query_loader.QUERIES_DIR

# Мапінг типу об'єкта 1С → тека верхнього рівня
TYPE_TO_DIR = {
    "Справочник": "catalogs",
    "Документ":   "documents",
}

# Мапінг примітивних типів 1С → внутрішній набір типів .json
PRIM_TYPE_MAP = {
    "Строка": "string",
    "Число":  "number",
    "Дата":   "date",
    "Булево": "boolean",
}

# Короткий псевдонім таблиці в .sel за типом об'єкта
TABLE_ALIAS = {
    "Справочник": "дов",
    "Документ":   "док",
}

# Системні поля за замовчуванням (для списків/форм).
# Кожне: key (аліас у .sel/.json), expr (вираз 1С; {a} = псевдонім таблиці), type, info.
# covers — імена стандартних реквізитів 1С, які це поле "покриває"
#          (щоб не дублювати їх у переліку решти реквізитів).
SYSTEM_FIELDS = {
    "Справочник": [
        {"key": "_ref",         "expr": "{a}.Ссылка",          "type": "ref",     "info": "[системне] посилання",          "covers": ["Ссылка"]},
        {"key": "_code",        "expr": "{a}.Код",             "type": "string",  "info": "[системне] код",                "covers": ["Код"]},
        {"key": "_description", "expr": "{a}.Наименование",    "type": "string",  "info": "[системне] найменування",       "covers": ["Наименование"]},
        {"key": "_marked",      "expr": "{a}.ПометкаУдаления", "type": "boolean", "info": "[системне] помітка на вилучення", "covers": ["ПометкаУдаления"]},
        {"key": "_parent",      "expr": "{a}.Родитель",        "type": "ref",     "info": "[системне] батько (група)",     "covers": ["Родитель"]},
        {"key": "_isfolder",    "expr": "{a}.ЭтоГруппа",       "type": "boolean", "info": "[системне] це група",           "covers": ["ЭтоГруппа"]},
    ],
    "Документ": [
        {"key": "_ref",     "expr": "{a}.Ссылка",       "type": "ref",    "info": "[системне] посилання",  "covers": ["Ссылка"]},
        {"key": "_version", "expr": "{a}.ВерсияДанных",  "type": "string", "info": "[системне] ВерсияДанных", "covers": ["ВерсияДанных"]},
        {"key": "_number",  "expr": "{a}.Номер",        "type": "string", "info": "[системне] номер",      "covers": ["Номер"]},
        {"key": "_date",    "expr": "{a}.Дата",         "type": "date",   "info": "[системне] дата",       "covers": ["Дата"]},
        {
            "key": "_status",
            "expr": "ВЫБОР КОГДА {a}.Проведен ТОГДА 1 КОГДА {a}.ПометкаУдаления ТОГДА 2 ИНАЧЕ 0 КОНЕЦ",
            "type": "number",
            "info": "[системне] стан: 0=не проведено, 1=проведено, 2=помічено на вилучення",
            "covers": ["Проведен", "ПометкаУдаления"],
        },
    ],
}


def _safe_segment(value: str, what: str) -> str:
    """Перевіряє, що сегмент шляху безпечний (без .., слешів, порожнечі).
    Захист від запису поза queries1c/ навіть у внутрішній адмінці."""
    v = str(value or "").strip()
    if not v:
        raise HTTPException(status_code=400, detail=f"Порожнє значення: {what}")
    if v in (".", ".."):
        raise HTTPException(status_code=400, detail=f"Недопустиме значення: {what}")
    if "/" in v or "\\" in v or "\x00" in v:
        raise HTTPException(status_code=400, detail=f"Недопустимі символи у: {what}")
    return v


def save_query(file_name: str, sel: str, meta: dict, username: str = "") -> dict:
    """Пише .sel + .json у теку об'єкта, перечитує loader.
    Перед перезаписом наявного — тимчасова копія старих файлів у temp/<username>/.
    Повертає {ok, query_name, path_sel, path_json, total_queries}."""

    # ── Валідація вмісту .json (джерело правди) ──
    if not isinstance(meta, dict):
        raise HTTPException(status_code=400, detail="Поле json має бути об'єктом")

    query_name = str(meta.get("query_name", "")).strip()
    if not query_name:
        raise HTTPException(status_code=400, detail="У json відсутнє query_name")

    object_type = str(meta.get("object_type", "")).strip()
    object_name = str(meta.get("object_name", "")).strip()
    if not object_type or not object_name:
        raise HTTPException(status_code=400, detail="У json відсутнє object_type або object_name")

    # ── Текст запиту ──
    sel_text = str(sel or "").strip()
    if not sel_text:
        raise HTTPException(status_code=400, detail="Порожній текст запиту (.sel)")

    # ── Тека за типом ──
    subdir = TYPE_TO_DIR.get(object_type)
    if not subdir:
        raise HTTPException(
            status_code=400,
            detail=f"Невідомий object_type '{object_type}' (очікується Справочник або Документ)",
        )

    # ── Ім'я файлу: явне або = query_name ──
    base_name = file_name if (file_name and str(file_name).strip()) else query_name
    base_name = _safe_segment(base_name, "file_name")
    object_name_safe = _safe_segment(object_name, "object_name")

    # ── Складання шляхів ──
    target_dir = os.path.join(QUERIES_DIR, subdir, object_name_safe)
    sel_path  = os.path.join(target_dir, base_name + ".sel")
    json_path = os.path.join(target_dir, base_name + ".json")

    # Додатковий захист: підсумковий шлях має лишатися всередині QUERIES_DIR
    root_abs = os.path.abspath(QUERIES_DIR)
    target_abs = os.path.abspath(target_dir)
    if target_abs != root_abs and not target_abs.startswith(root_abs + os.sep):
        raise HTTPException(status_code=400, detail="Шлях виходить за межі queries1c/")

    # ── Тимчасова копія ПЕРЕД перезаписом (крок назад) ──
    # Копіюємо старі версії лише якщо файли вже існують (перезапис, не створення).
    from .backup_service import backup_temp_files
    backup_temp_files([sel_path, json_path], username)

    # ── Запис (тека створюється, наявне перезаписується) ──
    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(sel_path, "w", encoding="utf-8") as f:
            f.write(sel_text + "\n")
        with open(json_path, "w", encoding="utf-8") as f:
            json_lib.dump(meta, f, ensure_ascii=False, indent=2)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Помилка запису файлів: {e}")

    # ── Гарячий перечит усієї теки в пам'ять loader ──
    query_loader.load_queries()

    return {
        "ok": True,
        "query_name": query_name,
        "path_sel":  os.path.relpath(sel_path, QUERIES_DIR),
        "path_json": os.path.relpath(json_path, QUERIES_DIR),
        "total_queries": len(query_loader.list_queries()),
    }


def read_query(query_name: str) -> dict:
    """Читає СИРІ файли .sel + .json одного запиту з диску (за _path з loader).
    Сирі — щоб зберегти коментарі в .sel і всі поля в .json (loader їх обрізає).
    Повертає {query_name, file, sel, meta}."""
    cfg = query_loader.get_query(query_name)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Запит '{query_name}' не знайдено")

    base = cfg.get("_path")
    if not base:
        raise HTTPException(status_code=500, detail="У запиті відсутній шлях до файлів (_path)")

    sel_path  = base + ".sel"
    json_path = base + ".json"

    try:
        with open(sel_path, "r", encoding="utf-8") as f:
            sel_raw = f.read()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Помилка читання .sel: {e}")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            meta_raw = json_lib.load(f)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Помилка читання .json: {e}")
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Некоректний .json: {e}")

    return {
        "query_name": query_name,
        "file":       cfg.get("_file", ""),
        "sel":        sel_raw,
        "meta":       meta_raw,
    }


def _applicable_system_fields(object_type: str, describe: dict) -> list:
    """Системні поля, доречні для конкретного об'єкта: включає поле, лише якщо його
    covers-реквізити реально існують (Родитель/ЭтоГруппа є ТІЛЬКИ в ієрархічних довідниках).
    Реквізити, що існують завжди (Ссылка/Код/... /Проведен/ВерсияДанных/Номер/Дата),
    вважаються наявними без перевірки describe."""
    present = set()
    for a in (describe.get("attributes", []) or []):
        nm = a.get("name", "")
        if nm:
            present.add(nm)
    ALWAYS = {"Ссылка", "Код", "Наименование", "ПометкаУдаления",
              "Проведен", "ВерсияДанных", "Номер", "Дата"}
    result = []
    for sf in SYSTEM_FIELDS.get(object_type, []):
        covers = sf.get("covers", [])
        if all((c in ALWAYS) or (c in present) for c in covers):
            result.append(sf)
    return result


def _map_attr_type(types: list) -> tuple:
    """Зводить types[] з describe до (внутрішній_тип, опис_складу).
    Повертає (type_str, type_info):
      - type_str: "ref" | "string" | "number" | "date" | "boolean"
      - type_info: людський опис складу типу (для info поля), напр. "→ Контрагенты" або "Строка"
    Складений тип — беремо перший елемент для type_str, повний склад — у type_info."""
    if not types:
        return "string", ""

    parts_info = []
    first_type = None
    for t in types:
        if t.get("kind") == "ref":
            obj = t.get("object", "")
            short = obj.split(".", 1)[1] if "." in obj else obj
            parts_info.append("→ " + short)
            if first_type is None:
                first_type = "ref"
        else:
            prim = t.get("name", "")
            parts_info.append(prim)
            if first_type is None:
                first_type = PRIM_TYPE_MAP.get(prim, "string")

    return (first_type or "string"), ", ".join(parts_info)


def generate_query(object_type: str, object_name: str, task: str = "",
                   current_sel: str = "", current_meta: dict = None) -> dict:
    """Чернетка запиту з describe об'єкта 1С. Сам тягне describe з 1С.
    task порожній → механічна болванка (всі реквізити рівним переліком).
    task заданий → генерація через AI-шар (той самий формат {sel, meta}).
      Якщо передано current_sel/current_meta — AI редагує наявний запит.
    Повертає {sel, meta} — БЕЗ запису на диск."""

    object_type = str(object_type or "").strip()
    object_name = str(object_name or "").strip()
    if not object_type or not object_name:
        raise HTTPException(status_code=400, detail="Потрібні object_type і object_name")

    if object_type not in TYPE_TO_DIR:
        raise HTTPException(
            status_code=400,
            detail=f"Невідомий object_type '{object_type}' (очікується Справочник або Документ)",
        )

    # ── Тягнемо опис об'єкта з 1С ──
    describe = call_onec_read(
        ONEC_METADATA_DESCRIBE_URL,
        {"type": object_type, "name": object_name},
        label="generate_query.describe",
    )

    # ── Гілка AI: якщо задано текстове завдання ──
    task = str(task or "").strip()
    if task:
        return _generate_query_ai(describe, task, current_sel=current_sel, current_meta=current_meta)

    # ── Механіка: системні поля згори + решта реквізитів ──
    attrs = describe.get("attributes", []) or []
    synonym = describe.get("synonym", "") or ""

    # Короткий псевдонім таблиці (док/дов)
    alias = TABLE_ALIAS.get(object_type, "т")

    # Системні поля, доречні саме для цього об'єкта (без ієрархічних для лінійних довідників)
    sys_fields = _applicable_system_fields(object_type, describe)

    # Множина стандартних реквізитів, покритих ДОДАНИМИ системними (щоб не дублювати нижче)
    covered = set()
    for sf in sys_fields:
        for c in sf.get("covers", []):
            covered.add(c)

    lines = []
    fields = []

    # 1) Системні поля згори
    for sf in sys_fields:
        expr = sf["expr"].replace("{a}", alias)
        lines.append(f"    {expr} КАК {sf['key']}")
        fields.append({"key": sf["key"], "type": sf["type"], "info": sf["info"]})

    # 2) Решта реквізитів (пропускаємо покриті системними)
    for a in attrs:
        name = a.get("name", "")
        if not name or name in covered:
            continue
        lines.append(f"    {alias}.{name} КАК {name}")

        type_str, type_info = _map_attr_type(a.get("types", []))
        info = a.get("synonym", "") or ""
        if type_info:
            info = (info + f" [{type_info}]").strip() if info else type_info
        fields.append({"key": name, "type": type_str, "info": info})

    select_body = ",\n".join(lines) if lines else "    *"
    sel = (
        f"// Чернетка запиту для {object_type}.{object_name}\n"
        f"// Згенеровано автоматично — відредагуйте перед збереженням\n"
        f"// (системні поля _* вгорі; приберіть зайве, задайте осмислені аліаси, додайте ГДЕ/фільтри)\n"
        f"ВЫБРАТЬ\n"
        f"{select_body}\n"
        f"ИЗ\n"
        f"    {object_type}.{object_name} КАК {alias}"
    )

    # ── .json: query_name порожній (задасть людина/AI) ──
    meta = {
        "query_name": "",
        "object_type": object_type,
        "object_name": object_name,
        "source_name": ONEC_SOURCE_NAME,
        "info": synonym,
        "fields": fields,
    }

    return {"sel": sel, "meta": meta}


def _generate_query_ai(describe: dict, task: str, current_sel: str = "", current_meta: dict = None) -> dict:
    """Генерація/редагування чернетки через AI-шар за завданням користувача.
    Якщо передано current_sel/current_meta — AI редагує наявний запит.
    Повертає {sel, meta}. Гарантує коректність object_type/object_name (перезаписує з describe)."""
    from .ai import get_ai
    from .ai.prompts.query_gen import SYSTEM_PROMPT, build_user_prompt

    # Системні поля, доречні для цього об'єкта (ієрархічні — лише коли є Родитель/ЭтоГруппа)
    obj_type = describe.get("type", "")
    alias = TABLE_ALIAS.get(obj_type, "т")
    sys_fields = []
    for sf in _applicable_system_fields(obj_type, describe):
        sys_fields.append({
            "key": sf["key"],
            "expr": sf["expr"].replace("{a}", alias),
            "type": sf["type"],
            "info": sf["info"],
        })

    user_prompt = build_user_prompt(
        describe, task, sys_fields=sys_fields, alias=alias,
        current_sel=current_sel, current_meta=current_meta,
    )
    result = get_ai().ask(user_prompt, system=SYSTEM_PROMPT, expect_json=True)

    data = result.data
    if not isinstance(data, dict) or "sel" not in data or "meta" not in data:
        raise HTTPException(status_code=502, detail="AI повернув несподівану структуру (очікувалось {sel, meta})")

    sel = str(data.get("sel", "")).strip()
    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise HTTPException(status_code=502, detail="AI: поле meta не є об'єктом")

    # object_type/object_name — джерело правди з describe (не довіряємо AI у прив'язці)
    meta["object_type"] = describe.get("type", "")
    meta["object_name"] = describe.get("name", "")
    # source_name — з конфігу джерела (не від AI)
    meta["source_name"] = ONEC_SOURCE_NAME
    # query_name лишаємо як запропонував AI (людина перевірить у редакторі)

    return {"sel": sel, "meta": meta}