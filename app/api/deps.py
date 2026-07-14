"""API asılılıqları — JWT autentifikasiya yoxlaması.

AUTH_ENABLED=false olduqda (default, lokal inkişaf üçün) yoxlama sönülüdür.
İstehsalda AUTH_ENABLED=true qoyun — bütün qorunan endpointlər
Authorization: Bearer <token> tələb edəcək.
"""
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

# auto_error=False — token yoxdursa özümüz aydın xəta qaytarırıq
_bearer = HTTPBearer(auto_error=False)


def require_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """Cari istifadəçinin adını qaytarır; token etibarsızdırsa 401."""
    settings = get_settings()
    if not settings.auth_enabled:
        return "dev"  # inkişaf rejimi — yoxlamasız

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization başlığı tələb olunur (Bearer token)",
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token etibarsızdır: {exc}",
        ) from exc
    return str(payload.get("sub", "unknown"))
