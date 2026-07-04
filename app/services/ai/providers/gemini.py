# gemini.py — адаптер Google Gemini (generativelanguage REST API).
# Ключ і модель — з .env: GEMINI_API_KEY, GEMINI_MODEL, GOOGLE_API_VERSION.

import os

import httpx
from fastapi import HTTPException

from ..base import AIProvider, AIResult

GEMINI_BASE = "https://generativelanguage.googleapis.com"


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.default_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.api_version = os.getenv("GOOGLE_API_VERSION", "v1beta")

    def ask(self, prompt: str, system: str = None, expect_json: bool = False, **opts) -> AIResult:
        if not self.api_key:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY не налаштовано")

        model = opts.get("model") or self.default_model
        url = f"{GEMINI_BASE}/{self.api_version}/models/{model}:generateContent"

        body = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            "generationConfig": {
                "temperature": opts.get("temperature", 0.2),
                "maxOutputTokens": opts.get("max_tokens", 4096),
            },
        }
        # Системна інструкція (Gemini v1beta підтримує system_instruction)
        if system:
            body["system_instruction"] = {"parts": [{"text": system}]}
        # Просимо суворий JSON на рівні API, якщо очікуємо JSON
        if expect_json:
            body["generationConfig"]["responseMimeType"] = "application/json"

        try:
            resp = httpx.post(
                url,
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json=body,
                timeout=60,
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Gemini недоступний: {exc}")

        if resp.status_code != 200:
            detail = f"Gemini HTTP {resp.status_code}: {resp.text[:300]}"
            raise HTTPException(status_code=502, detail=detail)

        data = resp.json()

        # Витягнути текст з першого кандидата
        text = ""
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            raise HTTPException(status_code=502, detail="Gemini: неочікувана структура відповіді")

        parsed = None
        if expect_json:
            try:
                parsed = AIResult.parse_json(text)
            except ValueError as e:
                raise HTTPException(status_code=502, detail=f"Gemini повернув невалідний JSON: {e}")

        return AIResult(text=text, raw=data, model=model, provider=self.name, data=parsed)