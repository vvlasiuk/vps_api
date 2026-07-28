from datetime import datetime

# Конфіг: довідник → {реквізит: функція, що повертає значення для fields}
# Додавання нового автозаповнення в майбутньому — просто новий запис тут,
# без змін у самому хендлері save_cat.
AUTOFILL_ON_CREATE = {
    "ПСТ_ВмістВідправлення": {
        "ДатаСтворення": lambda: {
            "type": "date",
            "value": datetime.now().isoformat(),
        },
    },
}


def apply_create_autofill(payload: dict) -> dict:
    """
    Домішує службові поля в payload save_cat, коли створюється НОВИЙ елемент
    довідника (ref порожній) і для цього довідника є запис в AUTOFILL_ON_CREATE.
    Не перезаписує поле, якщо воно вже прийшло від фронтенду.
    """
    catalog = payload.get("catalog")
    ref = payload.get("ref") or ""

    if ref == "" and catalog in AUTOFILL_ON_CREATE:
        fields = payload.setdefault("fields", {})
        for field_name, value_factory in AUTOFILL_ON_CREATE[catalog].items():
            if field_name not in fields:
                fields[field_name] = value_factory()

    return payload