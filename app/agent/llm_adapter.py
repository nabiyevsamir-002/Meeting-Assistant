"""Bizim LLM abstraksiyasını LangChain-ə "tanıdan" adapter.

LangChain-in LLM baza sinfini genişləndirir və çağırışları
BaseLLMProvider-ə ötürür. Beləliklə ReAct agent və Summary memory
mock/Claude/OpenAI provayderlərin HAMISI ilə eyni cür işləyir.
"""
from typing import Any, Optional

from langchain_core.language_models.llms import LLM
from pydantic import ConfigDict

from app.providers.llm.base import BaseLLMProvider


class ProviderLLM(LLM):
    """BaseLLMProvider -> LangChain LLM körpüsü."""

    provider: BaseLLMProvider
    system: Optional[str] = None

    # BaseLLMProvider pydantic modeli deyil — icazə veririk
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return f"provider-{self.provider.name}"

    def _call(
        self,
        prompt: str,
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> str:
        # ReAct agent stop=["\nObservation"] ötürür — provayderə çatdırırıq
        return self.provider.complete(prompt, system=self.system, stop=stop)

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"provider": self.provider.name}
