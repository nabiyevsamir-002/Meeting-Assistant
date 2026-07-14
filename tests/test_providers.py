"""Mock provayderlərin davranış testləri."""
from app.models.structured import ActionItems, AnswerOptions, DetectedQuestions
from app.prompts import DETECT_QUESTIONS, EXTRACT_ACTIONS, STRUCTURE_ANSWERS
from app.providers.embeddings import MockEmbeddingProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.stt.mock import MockSTTProvider
from app.providers.vector import InMemoryVectorStore, VectorPoint


def test_mock_llm_detects_questions():
    """"?" ilə bitən cümlələr sual kimi aşkarlanmalıdır."""
    llm = MockLLMProvider()
    prompt = DETECT_QUESTIONS.format(
        user_name="Samir",
        text="Layihə yaxşı gedir. Samir, deadline nə vaxtdır? Davam edək.",
    )
    result = llm.generate_structured(prompt, DetectedQuestions)
    assert len(result.questions) == 1
    assert "deadline" in result.questions[0].question
    assert result.questions[0].directed_to_user is True


def test_mock_llm_answer_options_have_three_tones():
    """Cavab variantları 3 fərqli tonda olmalıdır."""
    llm = MockLLMProvider()
    prompt = STRUCTURE_ANSWERS.format(
        question="Deadline nə vaxtdır?",
        context="Layihənin son tarixi 30 sentyabrdır.",
        draft="30 sentyabr.",
    )
    result = llm.generate_structured(prompt, AnswerOptions)
    assert len(result.options) == 3
    tones = {o.tone for o in result.options}
    assert tones == {"qısa", "ətraflı", "diplomatik"}


def test_mock_llm_extracts_action_items_with_owner():
    """Gələcək zaman felli cümlədən action item + məsul şəxs çıxmalıdır."""
    llm = MockLLMProvider()
    prompt = EXTRACT_ACTIONS.format(
        transcript="Samir sənədləri cümə gününə qədər hazırlayacaq."
    )
    result = llm.generate_structured(prompt, ActionItems)
    assert len(result.items) == 1
    assert result.items[0].owner == "Samir"
    assert result.items[0].due == "cümə"


def test_mock_llm_react_flow():
    """ReAct: ilk addım Action, Observation-dan sonra Final Answer."""
    llm = MockLLMProvider()
    base = "alətlər: search_context\nAction Input: ...\nBegin!\n\nQuestion: Deadline nə vaxtdır?\nThought:"
    first = llm.complete(base)
    assert "Action: search_context" in first
    assert "Final Answer" not in first

    second = llm.complete(base + first + "\nObservation: Son tarix 30 sentyabrdır.\nThought:")
    assert "Final Answer:" in second


def test_mock_stt_cycles_script():
    """Mock STT ssenari üzrə növbəti cümləni qaytarmalıdır."""
    stt = MockSTTProvider()
    first = stt.transcribe(b"fake-audio")
    second = stt.transcribe(b"fake-audio")
    assert first.text != second.text
    assert first.provider == "mock"


def test_mock_embeddings_deterministic_and_similar():
    """Eyni mətn eyni vektoru, oxşar mətn daha yaxın vektoru almalıdır."""
    emb = MockEmbeddingProvider(dim=64)
    v1 = emb.embed_one("layihənin deadline tarixi")
    v2 = emb.embed_one("layihənin deadline tarixi")
    assert v1 == v2  # determinizm

    store = InMemoryVectorStore()
    store.ensure_collection("test", 64)
    store.upsert("test", [
        VectorPoint(id="a", vector=emb.embed_one("layihənin deadline tarixi sentyabr"),
                    payload={"t": "deadline"}),
        VectorPoint(id="b", vector=emb.embed_one("naharda plov yedik"),
                    payload={"t": "yemək"}),
    ])
    hits = store.search("test", emb.embed_one("deadline nə vaxtdır layihənin"), top_k=2)
    # Ortaq sözlü sənəd birinci gəlməlidir
    assert hits[0].payload["t"] == "deadline"
