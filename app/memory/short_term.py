"""Qısamüddətli iclas yaddaşı — LangChain Window + Summary memory.

Hər canlı iclas üçün bir MeetingMemory obyekti yaradılır:
  - window:   son K seqmenti xatırlayır (ConversationBufferWindowMemory)
  - summary:  bütün iclasın artan xülasəsini saxlayır (ConversationSummaryMemory
              məntiqinin predict_new_summary metodu ilə)
  - entities: iclasda xatırlanan varlıqlar (öz sadə entity yaddaşımız)

Qeyd: LangChain 0.3-də bu yaddaş sinifləri "deprecated" statusundadır,
amma kurs mövzusunu göstərmək üçün qəsdən istifadə olunur.
"""
import warnings

from app.agent.llm_adapter import ProviderLLM
from app.memory.entity import EntityMemory
from app.providers.llm.base import BaseLLMProvider

# Deprecation xəbərdarlıqlarını səssizləşdiririk — davranış dəyişmir
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain")


class MeetingMemory:
    """Bir iclasın bütün qısamüddətli yaddaşını birləşdirir."""

    def __init__(self, llm_provider: BaseLLMProvider, window_size: int = 10) -> None:
        from langchain.memory import ConversationBufferWindowMemory, ConversationSummaryMemory
        from langchain_core.messages import HumanMessage

        self._HumanMessage = HumanMessage
        llm = ProviderLLM(provider=llm_provider)

        # Pəncərə yaddaşı — son K seqment ("k" LangChain parametridir)
        self.window = ConversationBufferWindowMemory(k=window_size, return_messages=True)
        # Xülasə yaddaşı — predict_new_summary ilə artan xülasə
        self._summary_memory = ConversationSummaryMemory(llm=llm)
        self.running_summary: str = ""
        # Varlıq yaddaşı
        self.entities = EntityMemory(llm_provider)
        # Yeni gələn, hələ xülasəyə salınmamış mesajlar
        self._pending: list = []

    def add_segment(self, text: str, speaker: str | None = None) -> None:
        """Yeni transkript seqmentini bütün yaddaş qatlarına əlavə edir."""
        line = f"[{speaker}] {text}" if speaker else text
        # Window yaddaşına yazırıq (input/output cütü tələb olunur)
        self.window.chat_memory.add_user_message(line)
        self._pending.append(self._HumanMessage(content=line))
        # Varlıqları yeniləyirik
        self.entities.update(text)

    def recent_window(self) -> str:
        """Son K seqmenti mətn kimi qaytarır (agentin aləti üçün)."""
        messages = self.window.chat_memory.messages
        return "\n".join(m.content for m in messages)

    def update_summary(self) -> str:
        """Yığılmış yeni mesajları artan xülasəyə əlavə edir."""
        if self._pending:
            self.running_summary = self._summary_memory.predict_new_summary(
                self._pending, self.running_summary
            )
            self._pending = []
        return self.running_summary
