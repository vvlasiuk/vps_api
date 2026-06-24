# query_loader.py — завантаження конфігів запитів 1С
# Сканує теку queries1c/, парує .sel (текст запиту) + .json (метадані)
# за іменем файлу. Викликається один раз при старті.

import os
import json
import re

# Тека з конфігами запитів (поряд з app/)
QUERIES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "queries1c")

# Мапа завантажених запитів: { "ref_contractors": {"query": "...", "info": "...", "fields": [...]} }
_queries = {}


def _strip_comments(text: str) -> str:
    """Видаляє рядки, що починаються з // (з урахуванням пробілів на початку)."""
    lines = text.splitlines()
    result = [ln for ln in lines if not ln.lstrip().startswith("//")]
    return "\n".join(result).strip()


def load_queries() -> dict:
    """Рекурсивно сканує QUERIES_DIR, завантажує всі .sel + парні .json.
    Повертає мапу запитів за іменем файлу (без розширення)."""
    global _queries
    _queries = {}

    if not os.path.isdir(QUERIES_DIR):
        print(f"[query_loader] Тека не знайдена: {QUERIES_DIR}")
        return _queries

    for root, dirs, files in os.walk(QUERIES_DIR):
        for filename in files:
            if not filename.endswith(".sel"):
                continue

            name = filename[:-4]  # ім'я без .sel
            sel_path = os.path.join(root, filename)
            json_path = os.path.join(root, name + ".json")

            # Текст запиту з .sel (без коментарів)
            try:
                with open(sel_path, "r", encoding="utf-8") as f:
                    query_text = _strip_comments(f.read())
            except Exception as e:
                print(f"[query_loader] Помилка читання {sel_path}: {e}")
                continue

            # Метадані з парного .json (необов'язковий)
            meta = {}
            if os.path.isfile(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                except Exception as e:
                    print(f"[query_loader] Помилка читання {json_path}: {e}")

            # Останній з однаковим іменем перемагає
            _queries[name] = {
                "query":  query_text,
                "info":   meta.get("info", ""),
                "fields": meta.get("fields", []),
            }

    print(f"[query_loader] Завантажено запитів: {len(_queries)}")
    return _queries


def get_query(name: str) -> dict | None:
    """Повертає конфіг запиту за іменем або None."""
    return _queries.get(name)


def list_queries() -> dict:
    """Повертає всі завантажені запити (для AI-агента / документації)."""
    return _queries