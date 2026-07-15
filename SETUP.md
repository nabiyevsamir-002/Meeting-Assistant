# SETUP.md — Açarlar, hesablar və quraşdırma

Sistem **heç bir açar olmadan** tam işləyir (mock rejim). Aşağıdakı açarları əlavə etdikcə uyğun hissələr canlı rejimə keçir. Bütün açarlar `.env` faylına yazılır (`cp .env.example .env`).

## Sürətli başlanğıc (açarsız)

```bash
make install      # .venv yaradır, asılılıqları qurur
make run          # http://localhost:8000 (UI: /ui/index.html, API: /docs)
make test         # pytest
make smoke        # uçdan-uca smoke test (serveri özü qaldırır)
```

Docker ilə (Qdrant + n8n daxil): `make compose-up`

---

## Açarlar və haradan alınır

### 1. Anthropic Claude (LLM) — əsas beyin
| | |
|---|---|
| Dəyişənlər | `LLM_PROVIDER=claude`, `ANTHROPIC_API_KEY` |
| Haradan | https://console.anthropic.com → API Keys → Create Key |
| Qiymət | Ödənişli (kredit əlavə etmək lazımdır); tələbə üçün $5 kifayətdir |
| Nəyi açır | Real sual aşkarlama, ReAct agent düşüncəsi, xülasə, action item-lər |

### 2. OpenAI (LLM əvəzləyicisi + Whisper + embedding)
| | |
|---|---|
| Dəyişənlər | `OPENAI_API_KEY`; LLM üçün `LLM_PROVIDER=openai`; STT üçün `STT_PROVIDER=whisper`; embedding üçün `EMBEDDING_PROVIDER=openai` |
| Haradan | https://platform.openai.com → API Keys |
| Qeyd | Claude embedding vermir → real semantik axtarış üçün bu açar lazımdır (`text-embedding-3-small`, çox ucuz). mem0 də bu açarı istifadə edir. |

### 3. ElevenLabs (STT Scribe + TTS) — FREE tier
| | |
|---|---|
| Dəyişənlər | `STT_PROVIDER=elevenlabs`, `ELEVENLABS_API_KEY` |
| Haradan | https://elevenlabs.io → qeydiyyat (pulsuz) → Profile → API Keys |
| Limit | Free tier: ayda məhdud dəqiqə — audio 20 saniyəlik parçalarla göndərilir, minimal istifadə üçün nəzərdə tutulub |
| Nəyi açır | Real transkripsiya (Scribe `scribe_v1`), istəyə bağlı TTS xülasə səsi |

### 4. Google Calendar (OAuth 2.0)
| | |
|---|---|
| Dəyişənlər | `CALENDAR_PROVIDER=google`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| Haradan | https://console.cloud.google.com → yeni layihə → "APIs & Services" → Calendar API-ni aktiv et → OAuth consent screen (External, test user kimi öz emailini əlavə et) → Credentials → OAuth Client ID (Web application) → Redirect URI: `http://localhost:8000/api/auth/google/callback` |
| Axın | Serveri qaldır → brauzerdə `http://localhost:8000/api/auth/google/login` → Google icazəsi → token `data/google_token.json`-a yazılır |

### 5. htmlcsstoimage (xülasə kartı)
| | |
|---|---|
| Dəyişənlər | `CARD_PROVIDER=hcti`, `HCTI_USER_ID`, `HCTI_API_KEY` |
| Haradan | https://htmlcsstoimage.com → qeydiyyat → Dashboard-da User ID + API Key (free tier: ayda 50 şəkil) |
| Mock | Açarsız kart HTML kimi `data/cards/` qovluğuna yazılır — brauzerdə açıb baxa bilərsiniz |

### 6. n8n (scraping + çatdırılma)
| | |
|---|---|
| Dəyişənlər | `DELIVERY_PROVIDER=n8n`, `N8N_DELIVERY_WEBHOOK_URL` |
| Quraşdırma | `docker compose up` ilə n8n avtomatik qalxır → http://localhost:5678 → hesab yarat → `n8n/scrape_ingest_workflow.json` və `n8n/delivery_workflow.json` fayllarını import et (Workflow menyusu → Import from File) → hər ikisini **Activate** et |
| n8n daxilində lazım olanlar | **SMTP credential** (email üçün — Gmail App Password: https://myaccount.google.com/apppasswords), **Telegram credential** (@BotFather-dən bot token), env dəyişənləri: `DELIVERY_FROM_EMAIL`, `DELIVERY_TO_EMAIL`, `TELEGRAM_CHAT_ID`, `OCR_SPACE_API_KEY` |
| OCR | https://ocr.space/ocrapi → pulsuz API key (şəkillərdən mətn üçün) |
| Mock | n8n olmadan çatdırılma `data/outbox/*.json` fayllarına yazılır |

### 7. BlackHole (Mac sistem səsi)
| | |
|---|---|
| Quraşdırma | `brew install blackhole-2ch` (restart tələb edir) → **Audio MIDI Setup** proqramı → sol aşağıda "+" → *Create Multi-Output Device* → həm dinamiklərinizi, həm BlackHole 2ch-i seçin → iclas zamanı sistem səs çıxışını bu Multi-Output-a keçirin |
| **Avtomatik rejim (tövsiyə)** | `bash capture/install_agent.sh` — bir dəfəlik. Bundan sonra Mac açılanda agent arxa planda işləyir və UI-da "Başlat" basdığınız an səsi özü tutmağa başlayır, "Bitir"də dayanır. Loglar: `~/Library/Logs/meeting-assistant-capture.log`. Silmək: `bash capture/uninstall_agent.sh` |
| Əl ilə rejim | `python capture/capture_blackhole.py --meeting-id <ID> --username <ad> --password <şifrə>` |
| Alternativ | BlackHole olmadan: `python capture/send_file.py --meeting-id <ID> --file iclas.wav` (fayl rejimi) |

### 8. Qdrant (vektor bazası)
Açar lazım deyil — `docker compose up` ilə lokal qalxır. Docker yoxdursa sistem avtomatik in-memory rejimə düşür (`VECTOR_BACKEND=auto`).

---

## Hansı açar hansı fazanı "canlı" edir

| Faza | Minimal canlı rejim üçün |
|------|--------------------------|
| Phase 1 (bilik bazası) | `OPENAI_API_KEY` (embedding) + Docker (Qdrant); scraping üçün n8n |
| Phase 1 (təqvim) | Google OAuth cütlüyü |
| Phase 2 (canlı iclas) | `ANTHROPIC_API_KEY` + `ELEVENLABS_API_KEY` + BlackHole |
| Phase 3 (hesabat) | `ANTHROPIC_API_KEY`; kart üçün HCTI; çatdırılma üçün n8n+SMTP/Telegram |
| Phase 4 (deploy) | DigitalOcean hesabı + domen (bax: DEPLOY.md) |

## Təhlükəsizlik qeydləri
- `.env` `.gitignore`-dadır — heç vaxt commit etməyin.
- İstehsalda `AUTH_ENABLED=true` və güclü `JWT_SECRET` (`openssl rand -hex 32`) qoyun.
- `data/google_token.json` da sirdir — droplet-də icazələri məhdudlaşdırın.
