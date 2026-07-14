# PLAN.md — Layihə fazaları və Month-4 kurs mövzularının xəritəsi

**Layihə:** AI Meeting Assistant — onlayn iclaslarda qeyd götürmə ehtiyacını aradan qaldıran sistem.

**Konsepsiya:** üç mərhələ — iclasdan **əvvəl** (bilik bazası), iclas **zamanı** (canlı sual aşkarlama + cavab təklifləri), iclasdan **sonra** (transkript, xülasə, action item-lər, çatdırılma).

---

## Faza → Kurs mövzusu xəritəsi

| Faza | Nə qurulub | Month-4 mövzusu | Kodda harada |
|------|-----------|-----------------|--------------|
| **0. Skelet** | FastAPI, pydantic-settings konfiqurasiyası, provayder abstraksiyası (hamısı mock ilə), docker-compose (app+Qdrant+n8n) | Deployment əsasları, layihə strukturu | `app/main.py`, `app/config.py`, `app/providers/`, `docker-compose.yml` |
| **1. İclasdan əvvəl** | Google Calendar OAuth 2.0 (əl ilə qurulmuş axın), n8n scraping/OCR/PDF workflow → `/api/ingest` → parçalama → embedding → Qdrant | **OAuth 2.0**, **Web Scraping (n8n, Cheerio/HTML extract, OCR API, PDF)**, vektor bazası | `app/providers/calendar/google.py`, `app/api/auth.py`, `n8n/scrape_ingest_workflow.json`, `app/ingestion/` |
| **2. İclas zamanı** | BlackHole/fayl rejimi audio tutma → ElevenLabs Scribe STT → sual aşkarlama (structured output) → LangChain **ReAct agent** (custom tool-lar) → cavab variantları → canlı feed | **Claude API (chat, tool use, structured output)**, **ElevenLabs STT**, **Tool Design (StructuredTool + Pydantic args_schema)**, **ReAct AgentExecutor (max_iterations, intermediate steps)**, qısamüddətli yaddaş | `capture/`, `app/providers/stt/`, `app/agent/`, `app/services/meeting_service.py` |
| **3. İclasdan sonra** | Transkript yığımı → yekun xülasə (Summary memory) → action item-lər (structured output / Instructor) → epizodik yaddaş (Qdrant) + mem0 → htmlcsstoimage kartı → n8n email/Telegram çatdırılması → istəyə bağlı TTS | **Structured output + Instructor**, **htmlcsstoimage**, **uzunmüddətli/epizodik yaddaş**, **mem0**, **LangGraph (StateGraph + MemorySaver)** | `app/services/post_meeting.py`, `app/memory/`, `app/providers/card.py`, `n8n/delivery_workflow.json` |
| **4. Deployment** | Prod Dockerfile (multi-stage), docker-compose.prod, nginx reverse proxy, Certbot HTTPS, GitHub Actions CI/CD, DEPLOY.md runbook | **Python app → DigitalOcean**, Docker, nginx, HTTPS, CI/CD | `deploy/`, `.github/workflows/ci.yml`, `DEPLOY.md` |

---

## Yaddaş arxitekturası (kurs mövzularının yaddaş hissəsi)

| Yaddaş növü | Texnologiya | Rol | Kod |
|-------------|-------------|-----|-----|
| Buffer/Window | LangChain `ConversationBufferWindowMemory` | Son K seqment — agentin "indi nə danışılır" konteksti | `app/memory/short_term.py` |
| Summary | LangChain `ConversationSummaryMemory.predict_new_summary` | İclasın artan xülasəsi — sürətli xülasə feed-i | `app/memory/short_term.py` |
| Entity | Custom (LLM structured output ilə) | Şəxslər/layihələr/tarixlər — hesabata düşür | `app/memory/entity.py` |
| Epizodik | Qdrant kolleksiyası (`meeting_episodes`) | "Keçən iclasda nə danışdıq?" — vektor axtarışı | `app/memory/episodic.py` |
| Uzunmüddətli | mem0 (real) / SQLite (mock) | İclaslar arası faktlar | `app/memory/long_term.py` |
| Checkpoint | LangGraph `MemorySaver` | İclas-sonrası pipeline-ın hər addımının vəziyyəti | `app/services/post_meeting.py` |

## Provayder abstraksiyası (bir env dəyişəni ilə keçid)

| Funksiya | Dəyişən | Variantlar |
|----------|---------|-----------|
| LLM | `LLM_PROVIDER` | `mock` \| `claude` \| `openai` |
| STT | `STT_PROVIDER` | `mock` \| `elevenlabs` (Scribe) \| `whisper` |
| TTS | `TTS_PROVIDER` | `mock` \| `elevenlabs` \| `openai` |
| Embedding | `EMBEDDING_PROVIDER` | `mock` \| `openai` |
| Vektor bazası | `VECTOR_BACKEND` | `auto` \| `qdrant` \| `memory` |
| Təqvim | `CALENDAR_PROVIDER` | `mock` \| `google` |
| Kart | `CARD_PROVIDER` | `mock` \| `hcti` |
| Çatdırılma | `DELIVERY_PROVIDER` | `mock` \| `n8n` |
| Uzunmüddətli yaddaş | `LONGTERM_PROVIDER` | `mock` \| `mem0` |

**Əsas prinsip:** hər provayderin mock variantı var → sistem SIFIR açarla uçdan-uca işləyir (`make smoke` bunu sübut edir). Real açar əlavə etmək yalnız mock-u canlı xidmətə "yüksəldir".
