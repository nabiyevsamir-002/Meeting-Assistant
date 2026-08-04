# AI İclas Köməkçisi — Layihə İcmalı (Master Sənəd)

> Bu sənəd layihənin **məqsədi, memarlığı və yol xəritəsi**ni bir yerə toplayır.
> Məqsəd: lokal fayllar silinsə belə, GitHub-dan `git clone` edib layihəni tam
> başa düşmək və davam etdirmək mümkün olsun. Sirlər (API açarları) bu sənəddə
> YOXDUR — onlar yalnız gitignore-dakı `.env`-də saxlanılır.

---

## 1. Məqsəd

**AI İclas Köməkçisi** — onlayn iclaslar üçün süni intellekt köməkçisidir. İclas
zamanı danışılanları real vaxtda mətnə çevirir, verilən sualları aşkarlayır və
yüklədiyin sənədlərə əsaslanaraq sənə **hazır cavab təklif edir**. İclasdan sonra
avtomatik **xülasə + tapşırıq siyahısı** hazırlayıb email və Telegram-a göndərir.
Beləliklə iclasda əl ilə qeyd götürmə ehtiyacı aradan qalxır.

---

## 2. Necə işləyir (üç mərhələ)

1. **İclasdan əvvəl** — PDF/mətn sənədlər bilik bazasına yüklənir (vektor bazası, RAG).
2. **İclas zamanı** — səs → canlı transkript → sual aşkarlama → sənədə əsaslanan cavab.
3. **İclasdan sonra** — xülasə + tapşırıqlar → email və Telegram-a (n8n ilə).

---

## 3. İstifadə olunan texnologiyalar

FastAPI · Claude API (LLM) · ElevenLabs (səs→mətn) · OpenAI embedding ·
LangChain (ReAct agent + yaddaş) · LangGraph (iclas-sonrası axın) · Qdrant (vektor
bazası) · mem0 (uzunmüddətli yaddaş) · SQLite · n8n (avtomatlaşdırma) · Docker ·
DigitalOcean + nginx + HTTPS.

**Əsas dizayn prinsipi:** hər xarici xidmətin **"mock" versiyası** var — sistem heç
bir API açarı olmadan da tam işləyir. Provayderlər tək bir mühit dəyişəni ilə
dəyişdirilir (məs. `LLM_PROVIDER=mock|claude|openai`). Bu, həm pulsuz demo, həm də
sınaq üçün kritikdir.

---

## 4. Memarlıq (qatlı struktur)

Layihə qatlıdır — hər qovluq bir məsuliyyət daşıyır:

| Qovluq | Rolu |
|---|---|
| `app/api/` | HTTP endpoint-lər (giriş nöqtələri) |
| `app/services/` | Əsas biznes məntiqi (canlı iclas + iclas-sonrası) |
| `app/providers/` | Xarici xidmətlər — **hər birinin mock-u var** (llm, stt, embeddings, vector, tts, card, delivery) |
| `app/agent/` | LangChain ReAct agent (düşün → alət → cavab) |
| `app/memory/` | Yaddaş qatları: qısamüddətli, uzunmüddətli (mem0), entity, epizodik |
| `app/ingestion/` | Bilik bazasına yükləmə: parçalama → embedding → Qdrant (RAG) |
| `app/models/` + `app/storage/` | Məlumat modelləri + SQLite (repo/CRUD) |
| `app/static/` | İnterfeys (`index.html` — Liquid Glass dizayn) |
| `capture/` | Mac səs tutma agenti (ElevenLabs) |
| `n8n/` | İki avtomatlaşdırma workflow-u (JSON): sənəd toplama + hesabat çatdırılması |
| `deploy/` | Prod Docker/nginx/HTTPS konfiqurasiyası |
| `tests/` | pytest test dəsti |

### "Ulduz" fayllar (layihənin ürəyi)
- `app/main.py` — FastAPI giriş nöqtəsi.
- `app/services/meeting_service.py` — ⭐ canlı axın: transkript → sual aşkarlama → cavab.
- `app/ingestion/service.py` + `app/providers/vector.py` — RAG (parçalama, embedding, axtarış).
- `app/agent/react_agent.py` — LangChain ReAct agent.
- `app/services/post_meeting.py` — iclas-sonrası (LangGraph: xülasə + tapşırıq + çatdırılma).
- `app/config.py` — mock/real provayder keçidi.

### Məlumat axını (qısa)
```
Səs → STT → transkript seqmenti
        → [kilid altında] yaddaş + sual aşkarlama (LLM) + dedup
        → [kiliddən kənar] RAG axtarışı + axan cavab
İclas bitəndə → LangGraph pipeline → xülasə/tapşırıq/kart → n8n → email + Telegram
```

---

## 5. Nə hazırdır (funksiyalar)

- Canlı transkript (nitqin real vaxtda mətnə çevrilməsi).
- Sual aşkarlama — xüsusən sizə ünvanlanan suallar seçilir.
- Sənədə əsaslanan (RAG) cavablar + güvən halqası.
- Öncədən hazırlanmış Q&A keşi — uyğun sualda ani cavab.
- İclas-sonrası avtomatik xülasə + tapşırıq siyahısı.
- n8n ilə email + Telegram çatdırılması.
- İclas tarixçəsi, axtarış və hesabatlar.
- Liquid Glass interfeys (Siri orbu, cari sual kapsulu).
- Tam mock rejim (açarsız işləyir) + prod deploy (Docker + HTTPS + CI/CD).

---

## 6. Son vəziyyət — bu mərhələdə həll olunan problemlər

Aşağıdakılar həll olunub və prod-a deploy edilib (dəqiqlik + sabitlik):

1. **Cavab dəqiqliyi** — kontekst modelə TAM verilir (əvvəl 200 simvola kəsilirdi
   və fakt itirdi → yanlış "sənəddə yoxdur"). `_build_context()`.
2. **Ən yeni sual öndə** — panel sıralaması xronolojidir (əvvəl köhnə ünvanlı sual
   yuxarı qalxıб yenisini 2-3-cü sıraya salırdı).
3. **Xəta-təhlükəsiz cavab** — keçici xətada kart "hazırlanır…"-da ilişmir,
   nəzakətli yekun verilir və təkrar cəhd olunur (`_answer_question_safe`).
4. **Donma/gecikmə** — SQLite **WAL** rejimi (paralel oxu/yazı bloklaşması bitdi) +
   cavab axını iclas kilidindən çıxarıldı (baş-sıra bloklanması aradan qalxdı).
5. **Bilik bazası qarışması** — yeni sənəd yüklənəndə köhnəsi **əvəzlənir**
   (`reset_knowledge_base`), UI-da 🗑 təmizləmə düyməsi + çoxlu fayl seçimi.
6. **Sual aşkarlanması STT təhrifinə davamlı** — prompt xam STT-ni nəzərə alır
   ("?"-siz, təhrif olunmuş sualları da tutur), prefilter genişləndirildi.
7. **Deploy yoxlaması** — `/health` cavabında `build` markeri (Actions rəngi deploy
   demək deyil — deploy addımları `continue-on-error`; həqiqəti bu marker göstərir).

---

## 7. Yol xəritəsi (növbəti addımlar)

Prioritetə görə, davam etmək istəyəndə:

1. **Dillərarası axtarış** — `embedding_dim` 256 → 512/768 qaldır və sənədləri
   **yenidən ingest** et. Az dilli sual ↔ ing. dilli sənəd recall-ı zəifdir;
   ölçünü artırmaq dəqiqliyi yaxşılaşdırır. (Qeyd: kolleksiya ölçüsü dəyişir,
   yenidən yükləmə lazımdır.)
2. **Kross-seqment sual aşkarlama** — bir sual iki seqmentə bölünəndə
   ("Əsas faktlar haqqında" + "nə bilirsiniz") birləşdirmək üçün kiçik kontekst
   pəncərəsi.
3. **Asinxron iclas bitirmə (`/end`)** — iclas-sonrası pipeline (xülasə/action/
   çatdırılma) hazırda sinxrondur, düymə 10-30s gözlədə bilir. Arxa plana keçirib
   düyməni ani etmək.
4. **`prepared_qa` həddinin tənzimlənməsi** — yanlış uyğunluq riskini azaltmaq
   (hazırda 0.86, zəif az embeddingində diqqətli olmaq lazımdır).
5. **Çoxdilli sənəd dəstəyi** — sənəd ingiliscə, sual azərbaycanca olduqda daha
   dayanıqlı axtarış (məs. sual/sənədi eyni dilə normallaşdırma).

---

## 8. Yenidən qurma və davam etdirmə

### A) Lokal, PULSUZ, açarsız (mock rejim) — işlədiyini göstərmək üçün
```bash
git clone https://github.com/nebiyevsamir002-star/meeting-assistant.git
cd meeting-assistant
docker compose up -d --build
# UI: http://localhost:8000/ui/index.html
```
Açar olmadan tam işləyir (bütün provayderlər mock).

### B) Real rejim (açarlarla) və ya prod deploy
- `.env`-i `.env.example`-dən köçür, **yeni** API açarları yaz.
- Lokal real rejim: `.env`-də `LLM_PROVIDER=claude`, `EMBEDDING_PROVIDER=openai` və s.
- Prod (DigitalOcean + HTTPS): **`DEPLOY.md`** addım-addım bələdçidir.

### Repo-da OLMAYAN (yenidən quranda lazım olacaq)
| Nə | Həlli |
|---|---|
| `.env` (real açarlar) | `.env.example`-dən köçür, yeni açarlar yaz |
| Server + IP | Yeni droplet aç → DuckDNS-i yeni IP-yə yönəlt → `deploy/activate_https.sh` |
| Yüklənmiş sənədlər (Qdrant) | Yenidən yüklə |
| İclas tarixçəsi (SQLite) | (Demo üçün lazım deyil) |
| n8n kredensialları (SMTP/Telegram) | Workflow JSON-ları repo-dadır → **Import**; kredensialları yenidən daxil et |

### Faydalı sənədlər (repo-da)
- `DEPLOY.md` — prod deploy runbook-u.
- `SETUP.md` — açarların mənbələri və lokal quraşdırma.
- `.env.example` — bütün mühit dəyişənlərinin şablonu.
- `n8n/*.json` — n8n workflow-ları (Import edilir).
- `Teqdimat_ve_Fayl_Strukturu.pdf`, `n8n_Workflow_Icmali.pdf` — təqdimat materialları.

---

## 9. Faydalı əmrlər

```bash
# Testlər
pytest tests/ -q

# Lokal işə salma (mock)
docker compose up -d --build

# Deploy vəziyyətini yoxla (prod işləyirsə)
curl -s https://<domen>/health   # "build" sahəsi cari versiyanı göstərir
```

---

*Bu sənəd yeniləndikcə saxlanılır. Layihəni davam etdirəndə əvvəlcə bunu oxu —
harada qaldığını və növbəti addımı buradan tapacaqsan.*
