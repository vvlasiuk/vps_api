# query_loader.py — завантаження конфігів запитів 1С
# Сканує теку queries1c/, парує .sel (текст запиту) + .json (метадані).
# Файли паруються за ІМЕНЕМ ФАЙЛУ (може бути кирилицею).
# Запит РЕЄСТРУЄТЬСЯ за полем "query_name" з .json (трансліт/ASCII-ідентифікатор).
# Прив'язка до об'єкта 1С — за полями "object_type" + "object_name" з .json.
# Викликається один раз при старті.

import os
import json

# Тека з конфігами запитів (поряд з app/)
QUERIES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "queries1c")

# Мапа завантажених запитів за query_name:
#   { "cat_contractors": {"query": "...", "info": "...", "fields": [...], "_file": "..."} }
_queries = {}


def _strip_comments(text: str) -> str:
    """Видаляє рядки, що починаються з // (з урахуванням пробілів на початку)."""
    lines = text.splitlines()
    result = [ln for ln in lines if not ln.lstrip().startswith("//")]
    return "\n".join(result).strip()


def load_queries() -> dict:
    """Рекурсивно сканує QUERIES_DIR, завантажує всі .sel + парні .json.
    Реєструє запити за полем query_name з .json.
    Повертає мапу запитів за query_name."""
    global _queries
    _queries = {}

    if not os.path.isdir(QUERIES_DIR):
        print(f"[query_loader] Тека не знайдена: {QUERIES_DIR}")
        return _queries

    for root, dirs, files in os.walk(QUERIES_DIR):
        for filename in files:
            if not filename.endswith(".sel"):
                continue

            file_base = filename[:-4]  # ім'я файлу без .sel (для парування й логів)
            sel_path  = os.path.join(root, filename)
            json_path = os.path.join(root, file_base + ".json")

            # Текст запиту з .sel (без коментарів)
            try:
                with open(sel_path, "r", encoding="utf-8") as f:
                    query_text = _strip_comments(f.read())
            except Exception as e:
                print(f"[query_loader] Помилка читання {sel_path}: {e}")
                continue

            # Метадані з парного .json — ТЕПЕР ОБОВ'ЯЗКОВІ (містять query_name)
            if not os.path.isfile(json_path):
                print(f"[query_loader] ПРОПУЩЕНО '{file_base}': немає парного .json (потрібен query_name)")
                continue

            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception as e:
                print(f"[query_loader] ПРОПУЩЕНО '{file_base}': помилка читання .json: {e}")
                continue

            # query_name — обов'язковий ідентифікатор реєстрації
            query_name = meta.get("query_name")
            if not query_name or not str(query_name).strip():
                print(f"[query_loader] ПРОПУЩЕНО '{file_base}': відсутнє поле query_name у .json")
                continue
            query_name = str(query_name).strip()

            # Захист від дублів query_name (два файли з однаковим ідентифікатором)
            if query_name in _queries:
                prev = _queries[query_name].get("_file", "?")
                print(f"[query_loader] УВАГА: дубль query_name '{query_name}' "
                      f"(файл '{file_base}' перезапише '{prev}')")

            _queries[query_name] = {
                "query":  query_text,
                "info":   meta.get("info", ""),
                "fields": meta.get("fields", []),
                "_file":  file_base,  # службове: з якого файлу завантажено (для діагностики)
                "_path":  os.path.join(root, file_base),  # база шляху без розширення (для читання сирих файлів)
                "_object_type": str(meta.get("object_type", "")).strip(),  # прив'язка до об'єкта 1С
                "_object_name": str(meta.get("object_name", "")).strip(),
                "_mcp_allowed": bool(meta.get("mcp_allowed", False)),  # доступ через MCP-канал (deny by default)
            }

    print(f"[query_loader] Завантажено запитів: {len(_queries)}")
    return _queries


def get_query(name: str) -> dict | None:
    """Повертає конфіг запиту за query_name або None."""
    return _queries.get(name)


def list_queries() -> dict:
    """Повертає всі завантажені запити (за query_name) — для AI-агента / документації."""
    return _queries


def list_queries_for_object(object_type: str, object_name: str) -> list:
    """Повертає запити, прив'язані до конкретного об'єкта 1С (за object_type + object_name з .json).
    Використовується браузером метаданих для показу наявних запитів об'єкта."""
    result = []
    for query_name, cfg in _queries.items():
        if cfg.get("_object_type") == object_type and cfg.get("_object_name") == object_name:
            result.append({
                "query_name": query_name,
                "info":       cfg.get("info", ""),
                "file":       cfg.get("_file", ""),
                "fields_count": len(cfg.get("fields", [])),
                "mcp_allowed": cfg.get("_mcp_allowed", False),  # чи доступний через MCP-канал
            })
    result.sort(key=lambda q: q["query_name"])
    return result