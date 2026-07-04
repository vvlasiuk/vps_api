# services.ai — мультипровайдерний AI-шар.
# Публічний інтерфейс:
#   from ..services.ai import get_ai
#   result = get_ai().ask(prompt, system="...", expect_json=True)
#   result.text / result.data

from .base import AIProvider, AIResult
from .factory import get_ai, list_providers

__all__ = ["get_ai", "list_providers", "AIProvider", "AIResult"]