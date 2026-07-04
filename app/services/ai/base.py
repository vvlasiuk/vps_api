# base.py — базовий інтерфейс AI-провайдера + уніфікований результат.
# Кожен провайдер (gemini, anthropic, ...) реалізує AIProvider.ask().
# Виклики з коду йдуть через services.ai.get_ai() — конкретний провайдер прихований.

import json as json_lib
from abc import ABC, abstractmethod


class AIResult:
    """Уніфікована відповідь моделі.
      text     : текст відповіді
      raw      : сира відповідь провайдера (dict) — для діагностики
      model    : фактична модель
      provider : ім'я провайдера ("gemini" / "anthropic")
      data     : розібраний JSON (лише якщо викликали з expect_json=True), інакше None
    """

    def __init__(self, text: str, raw=None, model: str = "", provider: str = "", data=None):
        self.text = text
        self.raw = raw
        self.model = model
        self.provider = provider
        self.data = data

    @staticmethod
    def parse_json(text: str):
        """Зачищає ```-фенси й парсить JSON з тексту відповіді.
        Повертає розібраний об'єкт або кидає ValueError."""
        t = (text or "").strip()
        # зняти ```json ... ``` або ``` ... ```
        if t.startswith("```"):
            # прибрати перший рядок з ``` (можливо ```json)
            nl = t.find("\n")
            if nl != -1:
                t = t[nl + 1:]
            # прибрати хвостові ```
            if t.rstrip().endswith("```"):
                t = t.rstrip()[:-3]
        t = t.strip()
        return json_lib.loads(t)


class AIProvider(ABC):
    """Базовий клас провайдера. name — коротке ім'я для логів/AIResult."""

    name = "base"

    @abstractmethod
    def ask(self, prompt: str, system: str = None, expect_json: bool = False, **opts) -> AIResult:
        """Синхронний запит до моделі.
          prompt      : текст запиту користувача
          system      : системна інструкція (опційно)
          expect_json : якщо True — розпарсити відповідь як JSON у AIResult.data
          **opts      : провайдер-специфічні опції (temperature, max_tokens, model...)
        """
        raise NotImplementedError