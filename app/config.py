"""Tətbiqin konfiqurasiyası (pydantic-settings).

Bütün parametrlər .env faylından və ya mühit dəyişənlərindən oxunur.
Sirlər (API açarları) HEÇ VAXT kodda saxlanmır — yalnız .env-də.
Heç bir açar olmadıqda bütün provayderlər avtomatik "mock" rejimə düşür.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Mərkəzi konfiqurasiya obyekti — .env → tipli sahələr."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",       # .env-də artıq dəyişən olsa xəta vermə
        case_sensitive=False,
    )

    # --- Ümumi ---
    app_name: str = "AI Meeting Assistant"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    # İstifadəçinin adı — sual aşkarlamada "bu sual bu şəxsə ünvanlanıb?" üçün
    # istifadə olunur (Chrome extension panelinin filtri də buna əsaslanır).
    user_name: str = "Samir"

    # --- Autentifikasiya (JWT) ---
    auth_enabled: bool = False
    # Daxili servislər (n8n) üçün API açarı — JWT müddəti bitən token əvəzinə
    # X-API-Key başlığı ilə sabit giriş imkanı verir
    internal_api_key: str = ""
    jwt_secret: str = "dev-secret-mutleq-deyisin-minimum-32-bayt-olsun"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120
    dev_username: str = "admin"
    dev_password: str = "admin123"

    # --- LLM provayderi: mock | claude | openai ---
    llm_provider: str = "mock"
    anthropic_api_key: str = ""
    # SÜRƏT: canlı iclas üçün ən sürətli Claude modeli (Haiku). Daha güclü,
    # amma daha yavaş cavab üçün ANTHROPIC_MODEL=claude-sonnet-5 verin.
    anthropic_model: str = "claude-haiku-4-5-20251001"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # --- LangSmith (LangChain izləmə/observability) ---
    # LANGSMITH_TRACING=true + açar verildikdə LangChain (ReAct agent, yaddaş)
    # avtomatik izlənir — hər addım smith.langchain.com-da görünür.
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "meeting-assistant"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # --- STT provayderi: mock | elevenlabs | whisper ---
    stt_provider: str = "mock"
    elevenlabs_api_key: str = ""
    elevenlabs_stt_model: str = "scribe_v1"
    whisper_model: str = "whisper-1"

    # --- TTS (istəyə bağlı): mock | elevenlabs | openai ---
    tts_enabled: bool = False
    tts_provider: str = "mock"
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_tts_model: str = "eleven_multilingual_v2"

    # --- Embedding: mock | openai ---
    embedding_provider: str = "mock"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 256

    # --- Vektor bazası: auto | qdrant | memory ---
    vector_backend: str = "auto"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection_context: str = "meeting_context"
    qdrant_collection_episodes: str = "meeting_episodes"

    # --- Uzunmüddətli yaddaş: mock | mem0 ---
    longterm_provider: str = "mock"

    # --- Xülasə kartı: mock | hcti ---
    card_provider: str = "mock"
    hcti_user_id: str = ""
    hcti_api_key: str = ""

    # --- Çatdırılma: mock | n8n ---
    delivery_provider: str = "mock"
    n8n_delivery_webhook_url: str = "http://localhost:5678/webhook/meeting-delivery"

    # --- Yaddaş ---
    sqlite_path: str = "data/app.db"
    data_dir: str = "data"

    # --- Pipeline parametrləri ---
    quick_summary_every: int = 5       # neçə seqmentdən bir sürətli xülasə
                                       # (xülasə 2 LLM çağırışıdır — qısa parçalarla
                                       # 3 çox tez-tez idi, 5 ≈ hər 35 saniyə)
    agent_max_iterations: int = 4      # ReAct agentin maksimum addım sayı
    # Canlı iclasda SÜRƏT üçün: ReAct agentin çox addımlı dövrünü atlayıb
    # birbaşa (axtarış + tək strukturlaşdırma çağırışı) cavab verir.
    # False → tam ReAct agent yolu (kurs nümayişi üçün, amma daha yavaş).
    live_fast_answers: bool = True
    # Yalnız istifadəçiyə ünvanlanan suallara cavab hazırla.
    # False (default) → BÜTÜN suallar cavablanır: real iclasda sual sizə aid
    # olsa da adınız həmişə çəkilmir ("Sən nə düşünürsən?"), ona görə bütün
    # sualları göstərmək daha etibarlıdır. Panel adınız keçənləri vurğulayır.
    answer_only_directed: bool = False
    chunk_size: int = 800              # sənəd parçalama ölçüsü (simvol)
    chunk_overlap: int = 150           # parçalar arası üst-üstə düşmə
    search_top_k: int = 6              # kontekst axtarışında nəticə sayı
    language: str = "az"

    # --- Sürət/dəqiqlik optimizasiyaları (A, C, D, E, J) ---
    # A: LLM sual aşkarlamadan ƏVVƏL lokal ön-filtr. Seqmentdə sual əlaməti
    # ("?", sual sözü, istifadəçi adı) yoxdursa LLM çağırışı TAM atlanır —
    # seqmentlərin çoxu adi cümlədir, beləliklə LLM yükü azalır, gecikmə düşür.
    local_prefilter: bool = True
    # C: eyni sual son N saniyədə cavablanıbsa təkrar aşkarlanıб-cavablanmır
    # (chunk sərhədləri üst-üstə düşəndə yaranan dublikatların qarşısını alır).
    answer_dedup_seconds: int = 60
    # J: PDF yüklənəndə arxa planda ehtimal olunan sual/cavab cütləri hazırlanır;
    # canlı sual onlardan biri ilə yüksək oxşarlıqla uyğun gəlirsə hazır cavab
    # DƏRHAL verilir (0 LLM çağırışı). Uyğunluq zəifdirsə adi RAG yoluna düşür.
    prepared_qa_enabled: bool = True
    prepared_qa_count: int = 12          # neçə ehtimal Q&A hazırlansın
    prepared_qa_threshold: float = 0.86  # uyğunluq həddi (konservativ — az sualı embeddingi zəif)

    def data_path(self, *parts: str) -> Path:
        """data/ qovluğu altında yol qurur və qovluğun mövcudluğunu təmin edir."""
        p = Path(self.data_dir).joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    """Keşlənmiş singleton — testlərdə cache_clear() ilə sıfırlanır."""
    return Settings()
