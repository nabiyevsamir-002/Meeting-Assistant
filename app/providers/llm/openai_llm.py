"""OpenAI LLM provayderi — Claude-un tam əvəzləyicisi.

LLM_PROVIDER=openai etməklə bütün sistem OpenAI üzərində işləyir.
Structured output üçün Instructor istifadə olunur.
"""
import logging
from typing import Optional

from app.providers.llm.base import BaseLLMProvider, TModel

logger = logging.getLogger(__name__)


class OpenAILLMProvider(BaseLLMProvider):
    """OpenAI Chat Completions üzərində complete + structured output."""

    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI  # yalnız bu provayder seçiləndə import olunur

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._api_key = api_key

    def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        stop: Optional[list[str]] = None,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or None,
        )
        return resp.choices[0].message.content or ""

    def generate_structured(
        self,
        prompt: str,
        schema: type[TModel],
        *,
        system: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> TModel:
        # Instructor OpenAI müştərisini "sarıyır" və response_model dəstəyi əlavə edir
        import instructor
        from openai import OpenAI

        client = instructor.from_openai(OpenAI(api_key=self._api_key))
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            response_model=schema,
        )
