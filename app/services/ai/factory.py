# factory.py — вибір активного AI-провайдера за .env (AI_PROVIDER).
# Кешує екземпляр (провайдери — легкі, читають конфіг у __init__).

import os

from fastapi import HTTPException

from .providers.anthropic import AnthropicProvider
from .providers.gemini import GeminiProvider

# Реєстр доступних провайдерів
_PROVIDERS = {
    "gemini": GeminiProvider,
    "anthropic": AnthropicProvider,
}

_instances = {}


def get_ai(provider: str = None):
    """Повертає активний провайдер. Якщо provider не заданий — береться AI_PROVIDER з .env.
    Екземпляри кешуються."""
    name = (provider or os.getenv("AI_PROVIDER", "gemini")).strip().lower()

    if name not in _PROVIDERS:
        raise HTTPException(
            status_code=500,
            detail=f"Невідомий AI_PROVIDER '{name}' (доступні: {', '.join(_PROVIDERS)})",
        )

    if name not in _instances:
        _instances[name] = _PROVIDERS[name]()
    return _instances[name]


def list_providers() -> list:
    """Список зареєстрованих провайдерів (для діагностики/UI)."""
    return list(_PROVIDERS.keys())