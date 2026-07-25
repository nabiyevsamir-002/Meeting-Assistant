# Lokal Demo — Müəllimə Göstərmək Üçün Addım-Addım

> Hər şey **lokal** işləyir, internet açarı TƏLƏB OLUNMUR (bütün provayderlər
> avtomatik mock rejimdədir). Giriş/şifrə də lazım deyil — lokalda auth sönülüdür.

## 1. Serveri başlat (PyCharm-da)

**Yol A — PyCharm Terminal (ən asan):**
1. PyCharm-da layihəni aç (`~/Desktop/Project`).
2. Aşağıdakı **Terminal** panelini aç və yaz:
   ```bash
   make run
   ```
3. Bu sətri görəndə hazırdır:
   `Uvicorn running on http://0.0.0.0:8000`

**Yol B — PyCharm Run Configuration (düymə ilə):**
1. Yuxarıda **Run → Edit Configurations… → + → Python**
2. Sahələri belə doldur:
   - **module** seç (script yox): `uvicorn`
   - **Parameters:** `app.main:app --reload --port 8000`
   - **Working directory:** layihənin kökü (`~/Desktop/Project`)
   - **Interpreter:** layihənin `.venv`-i
3. **OK** → yaşıl ▶ düyməsi ilə başlat.

## 2. UI-ı aç

Brauzerdə: **http://localhost:8000/ui/index.html**

(Yoxlama üçün: http://localhost:8000/health — `"status":"ok"` görünməlidir;
API sənədləri: http://localhost:8000/docs)

## 3. Demo ssenarisi (müəllimə göstəriləcək axın)

1. **İclas yarat** — mövzu yaz (məs. "Layihə müzakirəsi") → *Yarat*.
2. **Bilik bazası** kartında `Numune_Bilik_Bazasi.pdf` faylını yüklə
   (layihənin kökündə və Desktop-da var). Bu, "cavablar sənədə əsaslanır"
   hissəsini göstərmək üçündür.
3. **İclası başlat**.
4. **🎲 Nümunə cümlə (test)** düyməsini 4–6 dəfə bas — hər klik bir iclas
   cümləsi göndərir. Feed-də canlı görünəcək:
   - transkript seqmentləri;
   - **"Sual aşkarlandı — sizə ünvanlanıb"** (adı çəkilən sual) + sancaqlı
     **Son sual** paneli;
   - hər sual üçün **3 tonda cavab variantı** (qısa / ətraflı / diplomatik),
     PDF-ə əsaslananlar **📚** işarəsi ilə; cavaba klik → kopyalanır;
   - hər 3 seqmentdən bir **sürətli xülasə**.
5. **⏹ İclası bitir** — yekun hesabat açılır: xülasə, action item-lər,
   entity-lər, çatdırılma statusu.

Bütün bunlar mock rejimdə tam işləyir — kurs tələbi də məhz budur
(sistem sıfır açarla işləməlidir).

## 4. (İstəyə bağlı) Real AI ilə göstərmək

Real Claude/ElevenLabs cavabları istəsən, layihə kökündə `.env` yarat:
```
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
```
və serveri yenidən başlat. Açarlar `SETUP.md`-də izah olunub. Demo üçün
mütləq deyil.

## 5. Problemlər

| Problem | Həll |
|---|---|
| `make: command not found` və ya venv xətası | Terminala: `.venv/bin/python -m uvicorn app.main:app --reload --port 8000` |
| "Address already in use" (port məşğul) | `lsof -ti :8000 \| xargs kill -9` → yenidən başlat |
| UI login pəncərəsi açılır | Lokalda açılmamalıdır; açılıbsa köhnə tokendir — səhifəni yenilə (⌘⇧R) |
| Asılılıq xətası | Terminala: `make install` |

## 6. REAL Google Meet testi (künc paneli ilə)

> Ekranın küncündə, Meet-in ÜSTÜNDƏ üzən pəncərə: sizə ünvanlanan sual + cavablar.
> Ünvan: **http://localhost:8000/ui/panel.html**

1. `.env`-də açarlar hazırdır (ElevenLabs, Azure, OpenAI, Claude).
2. Terminal 1: `make run`
3. Brauzer: http://localhost:8000/ui/panel.html → PDF yüklə → **▶ İclası başlat**
4. Terminal 2 — **iki agent variantı var**:
   - **Azure streaming (SÜRƏTLİ, ~2-3s, default):** `.venv/bin/python capture/agent_stream.py`
   - Köhnə ElevenLabs (parça, ~6-10s, fallback): `.venv/bin/python capture/agent.py`
   → mikrofon icazəsi pəncərəsində **Allow**.
5. Meet-ə qoş (**qulaqlıqsız, dinamiklə!**) → paneldə **📌 Meet üzərinə çıxar**
6. Qarşı tərəf "Samir, …?" deyə sual verir → sual+cavablar küncdə görünür.

Vacib: qulaqlıq taxsanız mikrofon qarşı tərəfi eşitməz — səs dinamikdən gəlməlidir.

### Azure streaming agenti (`agent_stream.py`) haqqında
- Səsi FASİLƏSİZ Azure-a axıdır, `az-AZ` ilə canlı tanıyır, hazır mətni serverə göndərir.
- Azure açarı `.env`-dən (`AZURE_SPEECH_KEY`) və ya agent config-dən oxunur.
- **Qeyd (dəqiqlik):** Azure ingilis texniki terminlərdə (məs. "API") bəzən səhv edir;
  ElevenLabs (`agent.py`) belə terminlərdə daha dəqiqdir, amma yavaşdır. Terminlər çoxdursa
  fallback agenti işlət.
- Terminalда `Transkript: …` sətirləri görünürsə — Azure canlı tanıma işləyir.

## Qeyd

Chrome extension layihədən çıxarılıb (2026-07-23) — onun yerinə `panel.html`
(PiP künc paneli) gəldi. Prod server (visualkey.az) 2026-07-23-dən əlçatmazdır —
hər şey lokal işləyir. Səs tutma: `capture/` agenti terminaldan əl ilə işə salınır
(launchd deyil — mikrofon icazəsi məsələsi).
