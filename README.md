# 🎙 AI Meeting Assistant

Onlayn iclaslarda **qeyd götürmə ehtiyacını aradan qaldıran** AI köməkçi —
siz söhbətə fokuslanırsınız, sistem qalanını edir.

## Nə edir?

| Mərhələ | Funksiya |
|---------|----------|
| **İclasdan əvvəl** | Mövzu və sənədlər (veb, PDF, OCR) n8n workflow-u ilə yığılır, parçalanır, embedding-lənir və Qdrant bilik bazasına yüklənir. Google Calendar-dan yaxın iclaslar avtomatik hazırlanır (APScheduler). |
| **İclas zamanı** | Sistem səsi (BlackHole) 20 saniyəlik parçalarla ElevenLabs Scribe STT-dən keçir. AI verilən sualları aşkarlayır, sürətli xülasələr verir və qaçırdığınız suallar üçün bilik bazasına əsaslanan **2-3 cavab variantı** təklif edir (LangChain ReAct agent). |
| **İclasdan sonra** | Tam transkript, strukturlaşdırılmış xülasə, action item-lər, vizual xülasə kartı (htmlcsstoimage) və email/Telegram çatdırılması (n8n) avtomatik hazırlanır. İclas epizodik yaddaşa (Qdrant + mem0) yazılır. |

## Sürətli başlanğıc — açar TƏLƏB OLUNMUR

Bütün xarici xidmətlərin mock variantı var; sistem sıfır konfiqurasiya ilə işləyir:

```bash
make install    # virtual mühit + asılılıqlar
make run        # http://localhost:8000
```

- **UI (canlı feed):** http://localhost:8000/ui/index.html — "Yeni iclas" → "Başla" → "Demo seqment göndər"
- **API sənədləri:** http://localhost:8000/docs
- **Testlər:** `make test` &nbsp;•&nbsp; **Uçdan-uca smoke test:** `make smoke`

Docker ilə tam stack (FastAPI + Qdrant + n8n): `make compose-up`

Real API açarları əlavə etmək üçün: **[SETUP.md](SETUP.md)**. Hər faza hansı kurs mövzusunu əhatə edir: **[PLAN.md](PLAN.md)**. Serverə çıxarmaq: **[DEPLOY.md](DEPLOY.md)**.

## Arxitektura

```
                    ┌──────────── İclasdan əvvəl ────────────┐
  n8n (scraping/OCR/PDF) ──POST──> /api/ingest ──> chunker ──> embeddings ──> Qdrant
  Google Calendar (OAuth 2.0) ──> APScheduler ──> iclas hazırlığı

                    ┌──────────── İclas zamanı ──────────────┐
  BlackHole / WAV fayl ──> /segments/audio ──> STT (ElevenLabs|Whisper|mock)
      ──> sual aşkarlama (structured output)
      ──> ReAct agent (search_context, get_recent_transcript, detect_question)
      ──> 2-3 tonlu cavab variantı ──> canlı feed (polling UI)
      yaddaş: Window + Summary (LangChain) + Entity

                    ┌──────────── İclasdan sonra ────────────┐
  LangGraph StateGraph (MemorySaver):
    transkript ──> xülasə ──> action item-lər ──> epizodik yaddaş (Qdrant+mem0)
    ──> htmlcsstoimage kartı ──> n8n (email/Telegram)
```

## Provayder abstraksiyası

Hər xarici xidmət bir env dəyişəni ilə dəyişdirilir, açar yoxdursa avtomatik mock işləyir:

```
LLM_PROVIDER=mock|claude|openai      STT_PROVIDER=mock|elevenlabs|whisper
EMBEDDING_PROVIDER=mock|openai       VECTOR_BACKEND=auto|qdrant|memory
CALENDAR_PROVIDER=mock|google        CARD_PROVIDER=mock|hcti
DELIVERY_PROVIDER=mock|n8n           LONGTERM_PROVIDER=mock|mem0
```

## Layihə strukturu

```
app/
├── main.py            # FastAPI giriş nöqtəsi
├── config.py          # pydantic-settings (.env)
├── prompts.py         # bütün LLM prompt şablonları
├── runtime.py         # provayder singleton-ları
├── api/               # endpointlər: health, auth (JWT+OAuth), ingest, meetings, memory, calendar
├── providers/         # llm/, stt/, calendar/ + tts, embeddings, vector, card, delivery
├── agent/             # LangChain ReAct agent + StructuredTool-lar + LLM adapteri
├── memory/            # short_term (Window+Summary), entity, long_term (mem0), episodic
├── ingestion/         # chunker + embed + Qdrant
├── services/          # meeting_service (canlı pipeline), post_meeting (LangGraph), scheduler
├── models/            # Pydantic modelləri (domen + structured output sxemləri)
├── storage/           # SQLite (təmiz SQL repository)
└── static/            # demo UI (canlı feed izləyicisi)
capture/               # BlackHole tutucu + fayl rejimi göndəricisi
n8n/                   # 2 workflow JSON (scraping-ingest, çatdırılma)
deploy/                # Dockerfile.prod, compose.prod, nginx, (CI: .github/workflows)
tests/                 # pytest (15 test) + scripts/smoke_test.py
```

## Texnologiyalar
Python 3.11 • FastAPI • SQLite • APScheduler • Anthropic Claude / OpenAI •
Instructor • LangChain (ReAct, memory) • LangGraph • Qdrant • mem0 •
ElevenLabs (Scribe STT + TTS) • n8n • htmlcsstoimage • Docker • nginx • GitHub Actions
