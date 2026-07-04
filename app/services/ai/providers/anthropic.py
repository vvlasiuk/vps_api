# anthropic.py — адаптер Anthropic (Messages API).
# Ключ і модель — з .env: ANTHROPIC_API_KEY, ANTHROPIC_MODEL.

import os

import httpx
from fastapi import HTTPException

from ..base import AIProvider, AIResult

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.default_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    def ask(self, prompt: str, system: str = None, expect_json: bool = False, **opts) -> AIResult:
        if not self.api_key:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY не налаштовано")

        model = opts.get("model") or self.default_model

        body = {
            "model": model,
            "max_tokens": opts.get("max_tokens", 4096),
            "temperature": opts.get("temperature", 0.2),
            "messages": [
                {"role": "user", "content": prompt}
            ],
        }
        if system:
            body["system"] = system

        try:
            resp = httpx.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=60,
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Anthropic недоступний: {exc}")

        if resp.status_code != 200:
            detail = f"Anthropic HTTP {resp.status_code}: {resp.text[:300]}"
            raise HTTPException(status_code=502, detail=detail)

        data = resp.json()

        # Зібрати текст з блоків content (беремо text-блоки)
        text = ""
        try:
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
        except (AttributeError, TypeError):
            raise HTTPException(status_code=502, detail="Anthropic: неочікувана структура відповіді")

        if not text:
            raise HTTPException(status_code=502, detail="Anthropic: порожня відповідь")

        parsed = None
        if expect_json:
            try:
                parsed = AIResult.parse_json(text)
            except ValueError as e:
                raise HTTPException(status_code=502, detail=f"Anthropic повернув невалідний JSON: {e}")

        return AIResult(text=text, raw=data, model=model, provider=self.name, data=parsed)