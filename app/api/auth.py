"""Autentifikasiya endpointləri: JWT token verilməsi (dev login)."""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException
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
