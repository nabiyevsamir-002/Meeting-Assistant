"""LLM provayderlərinin baza interfeysi.

İki əməliyyat dəstəklənir:
  - complete():            sərbəst mətn cavabı (ReAct agent bundan istifadə edir)
  - generate_structured(): Pydantic sxeminə uyğun strukturlaşdırılmış cavab
"""
from abc import ABC, abstractmethod
from typing import Iterator, Optional, TypeVar

from pydantic import BaseModel

TModel = TypeVar("TModel", bound=BaseModel)


class BaseLLMProvider(ABC):
    """Bütün LLM provayderlərinin (mock, claude, openai) ortaq interfeysi."""

    name: str = "base"

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        stop: Optional[list[str]] = None,
    ) -> str:
        """Prompt-a sərbəst mətn cavabı qaytarır."""

    def stream(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        """Cavabı token-token axıdır (canlı yazılma effekti üçün).

        Default: axın dəstəklənmirsə tam cavabı bir dəfəyə verir. Claude/OpenAI
        bunu real streaming ilə əvəz edir.
        """
        yield self.complete(prompt, system=system, max_tokens=max_tokens)

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: type[TModel],
        *,
        system: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> TModel:
        """Cavabı verilmiş Pydantic sxeminə uyğun obyekt kimi qaytarır."""
