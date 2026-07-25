"""Anthropic Claude LLM provayderi.

Structured output üçün əvvəlcə Instructor kitabxanası sınanır
(kurs mövzusu), alınmazsa Claude-un native tool-use mexanizmi ilə
JSON sxemə məcburi cavab alınır.
"""
import logging
from typing import Optional

from app.providers.llm.base import BaseLLMProvider, TModel

logger = logging.getLogger(__name__)


class ClaudeLLMProvider(BaseLLMProvider):
    """Claude API üzərində complete + structured output."""

    name = "claude"

    # İlişən bir çağırış pipeline-ı dəqiqələrlə saxlamasın
    _TIMEOUT = 60.0

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic  # yalnız bu provayder seçiləndə import olunur

        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=self._TIMEOUT, max_retries=1
        )
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
        # Qeyd: yeni Claude modelləri (claude-sonnet-5 və sonrası) temperature
        # parametrini qəbul etmir — ötürülərsə 400 xətası qayıdır.
        # Köhnə modellərlə uyğunluq üçün əvvəl temperature ilə cəhd edirik,
        # rədd edilərsə parametrsiz təkrarlayırıq.
        kwargs: dict = dict(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        if system:
            kwargs["system"] = system
        if stop:
            # ReAct agent "\nObservation" stop ardıcıllığını ötürür
            kwargs["stop_sequences"] = [s for s in stop if s.strip()]
        try:
            resp = self._client.messages.create(**kwargs, temperature=temperature)
        except Exception as exc:  # noqa: BLE001
            if "temperature" not in str(exc):
                raise
            resp = self._client.messages.create(**kwargs)
        return "".join(b.text for b in resp.content if b.type == "text")

    def stream(self, prompt, *, system=None, max_tokens=1024):  # noqa: ANN001
        """Cavabı token-token axıdır (Claude native streaming)."""
        kwargs: dict = dict(model=self._model, max_tokens=max_tokens,
                            messages=[{"role": "user", "content": prompt}])
        if system:
            kwargs["system"] = system
        with self._client.messages.stream(**kwargs) as s:
            for text in s.text_stream:
                if text:
                    yield text

    def generate_structured(
        self,
        prompt: str,
        schema: type[TModel],
        *,
        system: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> TModel:
        # 1-ci yol: Instructor — Pydantic sxemi birbaşa response_model kimi verilir
        try:
            import anthropic
            import instructor

            client = instructor.from_anthropic(
                anthropic.Anthropic(api_key=self._api_key, timeout=self._TIMEOUT, max_retries=1)
            )
            messages = [{"role": "user", "content": prompt}]
            return client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system or "Cavabı yalnız tələb olunan strukturda ver.",
                messages=messages,
                response_model=schema,
            )
        except Exception as exc:  # noqa: BLE001 — istənilən xətada fallback
            logger.warning("Instructor alınmadı (%s), tool-use fallback işlədilir", exc)

        # 2-ci yol: Claude native tool-use — sxem "alət" kimi təqdim olunur
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system or "Nəticəni emit_result aləti ilə qaytar.",
            messages=[{"role": "user", "content": prompt}],
            tools=[{
                "name": "emit_result",
                "description": "Strukturlaşdırılmış nəticəni qaytarır",
                "input_schema": schema.model_json_schema(),
            }],
            tool_choice={"type": "tool", "name": "emit_result"},
        )
        for block in resp.content:
            if block.type == "tool_use":
                return schema.model_validate(block.input)
        raise RuntimeError("Claude tool-use cavabında strukturlaşdırılmış blok tapılmadı")
