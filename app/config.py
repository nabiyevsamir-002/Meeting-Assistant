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
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

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

    # --- Google Calendar (OAuth 2.0): mock | google ---
    calendar_provider: str = "mock"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

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

    # --- Planlayıcı ---
    scheduler_enabled: bool = True
    calendar_poll_minutes: int = 5
    calendar_lookahead_minutes: int = 30

    # --- Pipeline parametrləri ---
    quick_summary_every: int = 3       # neçə seqmentdən bir sürətli xülasə
    agent_max_iterations: int = 4      # ReAct agentin maksimum addım sayı
    chunk_size: int = 800              # sənəd parçalama ölçüsü (simvol)
    chunk_overlap: int = 150           # parçalar arası üst-üstə düşmə
    search_top_k: int = 4              # kontekst axtarışında nəticə sayı
    language: str = "az"

    def data_path(self, *parts: str) -> Path:
        """data/ qovluğu altında yol qurur və qovluğun mövcudluğunu təmin edir."""
        p = Path(self.data_dir).joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    """Keşlənmiş singleton — testlərdə cache_clear() ilə sıfırlanır."""
    return Settings()
