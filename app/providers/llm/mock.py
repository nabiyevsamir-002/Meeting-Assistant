"""Mock LLM provayderi — API açarı olmadan bütün pipeline-ı işlədir.

Necə işləyir:
  - complete():  prompt-un növünü tanıyır (ReAct agent, xülasə və s.) və
                 uyğun formatda inandırıcı cavab qurur. ReAct üçün əvvəlcə
                 "Action: search_context", sonra "Final Answer: ..." qaytarır —
                 beləliklə AgentExecutor real alət çağırışı dövrü icra edir.
  - generate_structured(): prompt-dakı <mətn>, <sual> kimi taqlardan məlumatı
                 qaydalarla çıxarıb sxemə uyğun obyekt qurur (məs. "?" ilə
                 bitən cümlələr sual sayılır).

Real açar əlavə olunanda bu sinif eyni interfeysli Claude/OpenAI ilə əvəzlənir.
"""
import re
from typing import Optional

from pydantic import BaseModel

from app.models.structured import (
    ActionItem,
    ActionItems,
    AnswerOption,
    AnswerOptions,
    DetectedQuestion,
    DetectedQuestions,
    Entity,
    EntityList,
    MeetingSummaryModel,
    QuickSummary,
)
from app.providers.llm.base import BaseLLMProvider, TModel

# Azərbaycan əlifbasının böyük hərfləri (entity aşkarlama üçün)
_UPPER = "A-ZƏÖÜĞİŞÇ"

# Action item-ləri tanımaq üçün gələcək zaman felləri
_ACTION_VERBS = (
    "hazırlayacaq", "edəcək", "yazacaq", "göndərəcək", "təqdim edəcək",
    "yoxlayacaq", "quracaq", "planlaşdıracaq", "təhvil verəcək", "araşdıracaq",
)


def _tag(prompt: str, tag: str) -> str:
    """Prompt-dan <tag>...</tag> arasındakı mətni çıxarır."""
    m = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", prompt, re.DOTALL)
    return m.group(1) if m else ""


def _sentences(text: str) -> list[str]:
    """Mətni sadə qaydalarla cümlələrə bölür (durğu işarəsi saxlanılır)."""
    parts = re.findall(r"[^.!?\n]+[.!?]?", text)
    return [p.strip() for p in parts if p.strip()]


class MockLLMProvider(BaseLLMProvider):
    """Kanned (əvvəlcədən hazırlanmış) amma kontekstə həssas cavablar qaytaran provayder."""

    name = "mock"

    # --- Sərbəst mətn cavabı ---

    def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        stop: Optional[list[str]] = None,
    ) -> str:
        full = f"{system or ''}\n{prompt}"

        # 1) ReAct agent prompt-u: "Begin!" + "Action Input" işarələri var
        if "Action Input" in full and "Begin!" in full:
            return self._react_step(full)

        # 2) LangChain ConversationSummaryMemory prompt-u
        if "Progressively summarize" in full:
            return self._running_summary(full)

        # 3) Ümumi hal — qısa canned cavab
        return "Mock cavab: real LLM açarı əlavə olunanda bu cavab canlı modeldən gələcək."

    def _react_step(self, prompt: str) -> str:
        """ReAct dövrünün bir addımını imitasiya edir.

        İlk çağırışda alətə müraciət (Action), alət nəticəsi (Observation)
        görünəndən sonra isə yekun cavab (Final Answer) qaytarılır.

        Vacib incəlik: şablonun təlimat hissəsində də "Observation" sözü keçir,
        ona görə yalnız "Begin!"-dən SONRAKI real dialoq hissəsinə baxırıq.
        """
        tail = prompt.split("Begin!", 1)[-1]

        question = ""
        m = re.search(r"Question:\s*(.+)", tail)
        if m:
            question = m.group(1).strip()

        if "\nObservation" in tail:
            # Alət artıq işləyib — son Observation-u götürüb yekun cavab quraq
            obs_matches = re.findall(r"Observation:\s*(.+?)(?=\nThought:|\Z)", tail, re.DOTALL)
            context = obs_matches[-1].strip()[:300] if obs_matches else ""
            draft = (
                f"Sual: «{question}». "
                f"Bilik bazasındakı məlumata əsasən: {context or 'kontekst tapılmadı'}"
            )
            return (
                "Kontekstdən lazımi məlumatı topladım, indi cavab variantlarını hazırlaya bilərəm.\n"
                f"Final Answer: {draft}"
            )

        # İlk addım — bilik bazasında axtarış aparaq
        return (
            "Bu suala əsaslandırılmış cavab vermək üçün bilik bazasında axtarış aparmalıyam.\n"
            "Action: search_context\n"
            f"Action Input: {question or 'iclas mövzusu'}"
        )

    def _running_summary(self, prompt: str) -> str:
        """ConversationSummaryMemory üçün artan xülasə qurur."""
        m = re.search(r"New lines of conversation:\s*(.*?)\s*New summary:", prompt, re.DOTALL)
        new_lines = m.group(1).strip() if m else ""
        sents = _sentences(new_lines.replace("Human:", "").replace("AI:", ""))
        core = " ".join(sents[:2])[:400]
        return f"İclasda müzakirə davam edir. {core}"

    # --- Strukturlaşdırılmış cavab ---

    def generate_structured(
        self,
        prompt: str,
        schema: type[TModel],
        *,
        system: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> TModel:
        # Sxemin adına görə uyğun qayda-əsaslı "parser" seçilir
        builders = {
            "DetectedQuestions": self._detect_questions,
            "AnswerOptions": self._answer_options,
            "MeetingSummaryModel": self._meeting_summary,
            "ActionItems": self._action_items,
            "EntityList": self._entities,
            "QuickSummary": self._quick_summary,
        }
        builder = builders.get(schema.__name__)
        if builder:
            return builder(prompt)  # type: ignore[return-value]
        return self._generic_fill(schema)

    def _detect_questions(self, prompt: str) -> DetectedQuestions:
        """<mətn> içindəki "?" ilə bitən cümlələri sual kimi qaytarır."""
        text = _tag(prompt, "mətn")
        questions: list[DetectedQuestion] = []
        for sent in _sentences(text):
            if not sent.endswith("?"):
                continue
            # İstifadəçinin adı çəkilibsə və ya "siz" müraciəti varsa — ona ünvanlanıb
            directed = bool(re.search(r"\b(Samir|siz|sizcə|sən)\b", sent, re.IGNORECASE))
            questions.append(
                DetectedQuestion(
                    question=sent,
                    directed_to_user=directed,
                    urgency="yüksək" if directed else "normal",
                    confidence=0.9,
                )
            )
        return DetectedQuestions(questions=questions)

    def _answer_options(self, prompt: str) -> AnswerOptions:
        """Sual + kontekstdən 3 fərqli tonda cavab variantı qurur."""
        question = _tag(prompt, "sual") or "Sual"
        context = _tag(prompt, "kontekst")
        has_ctx = bool(context and "tapılmadı" not in context)
        snippet = _sentences(context)[0][:200] if has_ctx and _sentences(context) else ""
        options = [
            AnswerOption(
                text=(f"Qısa cavab: {snippet}" if snippet
                      else "Bu barədə dəqiq məlumatı yoxlayıb bir azdan qayıdım."),
                tone="qısa", based_on_context=has_ctx,
            ),
            AnswerOption(
                text=(f"Ətraflı desək: {snippet} Əlavə detalları sənədlərdə dəqiqləşdirib "
                      f"iclasdan sonra paylaşa bilərəm." if snippet
                      else "Bu mövzunu komanda ilə müzakirə edib ətraflı cavabı sonra təqdim edim."),
                tone="ətraflı", based_on_context=has_ctx,
            ),
            AnswerOption(
                text="Yaxşı sualdır — gəlin bunu növbəti gündəm bəndi kimi qeyd edək və "
                     "məsul şəxslə birlikdə dəqiqləşdirək.",
                tone="diplomatik", based_on_context=False,
            ),
        ]
        return AnswerOptions(question=question, options=options)

    def _meeting_summary(self, prompt: str) -> MeetingSummaryModel:
        """Transkriptdən sadə qaydalarla yekun xülasə qurur."""
        transcript = _tag(prompt, "transkript")
        topic_m = re.search(r"İclasın mövzusu:\s*(.+)", prompt)
        topic = topic_m.group(1).strip() if topic_m else "İclas"
        sents = _sentences(transcript)
        key_points = [s for s in sents if not s.endswith("?")][:4]
        open_qs = [s for s in sents if s.endswith("?")][:3]
        return MeetingSummaryModel(
            headline=f"{topic} üzrə müzakirə aparıldı",
            overview=(
                f"İclasda «{topic}» mövzusu müzakirə olundu. "
                f"Ümumilikdə {len(sents)} fikir səsləndi, əsas məqamlar və "
                f"növbəti addımlar razılaşdırıldı."
            ),
            key_points=key_points or ["Müzakirə aparıldı"],
            decisions=["Növbəti addımlar üzrə razılıq əldə olundu"] if sents else [],
            open_questions=open_qs,
        )

    def _action_items(self, prompt: str) -> ActionItems:
        """Gələcək zaman felli cümlələrdən action item-lər çıxarır."""
        transcript = _tag(prompt, "transkript")
        items: list[ActionItem] = []
        for sent in _sentences(transcript):
            if not any(v in sent.lower() for v in _ACTION_VERBS):
                continue
            owner_m = re.match(rf"\s*([{_UPPER}][a-zəöüğışç]+)", sent)
            due_m = re.search(
                r"(bazar ertəsi|çərşənbə axşamı|çərşənbə|cümə axşamı|cümə|şənbə|bazar"
                r"|sabah|gələn həftə|ayın \d+-nə?|\d+ gün ərzində)",
                sent, re.IGNORECASE,
            )
            items.append(
                ActionItem(
                    task=sent,
                    owner=owner_m.group(1) if owner_m else None,
                    due=due_m.group(1) if due_m else None,
                    priority="orta",
                )
            )
        if not items:
            items.append(
                ActionItem(task="İclas xülasəsini komanda ilə paylaşmaq",
                           owner=None, due=None, priority="orta")
            )
        return ActionItems(items=items)

    def _entities(self, prompt: str) -> EntityList:
        """Cümlə ortasındakı böyük hərfli sözləri varlıq kimi çıxarır."""
        text = _tag(prompt, "mətn")
        entities: dict[str, Entity] = {}
        for sent in _sentences(text):
            words = sent.split()
            # İlk sözü buraxırıq — cümlə başı onsuz da böyük hərflə başlayır
            for w in words[1:]:
                clean = w.strip(".,!?:;«»\"'()")
                if re.fullmatch(rf"[{_UPPER}][a-zəöüğışç]{{2,}}", clean) and clean not in entities:
                    entities[clean] = Entity(
                        name=clean, type="şəxs",
                        note=f"İclasda xatırlanıb: «{sent[:80]}»",
                    )
        return EntityList(entities=list(entities.values())[:6])

    def _quick_summary(self, prompt: str) -> QuickSummary:
        """Son pəncərədən 2 cümləlik cari vəziyyət icmalı qurur."""
        window = _tag(prompt, "mətn")
        sents = _sentences(window)
        last = " ".join(sents[-2:])[:300] if sents else "Müzakirə davam edir."
        return QuickSummary(
            summary=f"Söhbətin cari vəziyyəti: {last}",
            current_topic=sents[-1][:80] if sents else "",
        )

    def _generic_fill(self, schema: type[TModel]) -> TModel:
        """Naməlum sxemlər üçün sahə tiplərinə görə standart dəyərlər doldurur."""
        values = {}
        for name, field in schema.model_fields.items():
            ann = field.annotation
            if ann is str:
                values[name] = "mock"
            elif ann is int:
                values[name] = 0
            elif ann is float:
                values[name] = 0.0
            elif ann is bool:
                values[name] = False
            else:
                # list, dict, Optional və s. üçün default varsa ona güvənirik
                if field.default is not None or field.default_factory is not None:
                    continue
                values[name] = None
        return schema.model_validate(values)
