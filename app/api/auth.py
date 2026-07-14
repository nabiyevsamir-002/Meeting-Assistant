"""Autentifikasiya endpointləri: JWT token + Google OAuth 2.0 axını."""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter()


class TokenRequest(BaseModel):
    """Dev login sorğusu — istifadəçi adı/şifrə .env-dən yoxlanılır."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT cavabı."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/token", response_model=TokenResponse)
def issue_token(req: TokenRequest) -> TokenResponse:
    """Dev istifadəçisi üçün JWT verir (istehsalda real istifadəçi bazası olmalıdır)."""
    settings = get_settings()
    if req.username != settings.dev_username or req.password != settings.dev_password:
        raise HTTPException(status_code=401, detail="İstifadəçi adı və ya şifrə yanlışdır")

    expires = timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": req.username,
        "exp": datetime.now(timezone.utc) + expires,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return TokenResponse(access_token=token, expires_in=int(expires.total_seconds()))


# --- Google OAuth 2.0 axını (Calendar üçün) ---

@router.get("/google/login")
def google_login():
    """İstifadəçini Google icazə səhifəsinə yönləndirir."""
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        # Açar yoxdursa aydın izah qaytarırıq — SETUP.md-yə istinadla
        raise HTTPException(
            status_code=501,
            detail=(
                "Google OAuth konfiqurasiya olunmayıb. SETUP.md-də göstərildiyi kimi "
                "GOOGLE_CLIENT_ID və GOOGLE_CLIENT_SECRET əlavə edin. "
                "Bu vaxta qədər CALENDAR_PROVIDER=mock işləyir."
            ),
        )
    from app.providers.calendar.google import build_auth_url

    return RedirectResponse(build_auth_url(settings))


@router.get("/google/callback")
def google_callback(code: str = "", error: str = ""):
    """Google-dan qayıdan authorization code-u token-ə dəyişir."""
    settings = get_settings()
    if error:
        raise HTTPException(status_code=400, detail=f"Google icazə xətası: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="code parametri yoxdur")

    from app.providers.calendar.google import exchange_code

    exchange_code(settings, code)
    # Uğurlu — istifadəçini UI-a qaytarırıq
    return RedirectResponse("/ui/index.html?google=ok")
