"""JWT autentifikasiya testləri."""


def test_token_issued_with_valid_credentials(client):
    """Düzgün dev istifadəçi məlumatları ilə token verilməlidir."""
    resp = client.post("/api/auth/token",
                       json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]


def test_token_rejected_with_wrong_password(client):
    """Yanlış şifrə 401 qaytarmalıdır."""
    resp = client.post("/api/auth/token",
                       json={"username": "admin", "password": "yanlış"})
    assert resp.status_code == 401


def test_protected_endpoint_requires_token_when_auth_enabled(client, monkeypatch):
    """AUTH_ENABLED=true olduqda token olmadan 401, token ilə 200."""
    from app.config import get_settings

    # Keşlənmiş settings obyektində auth-u müvəqqəti aktivləşdiririk
    monkeypatch.setattr(get_settings(), "auth_enabled", True)

    resp = client.get("/api/meetings")
    assert resp.status_code == 401

    token = client.post("/api/auth/token",
                        json={"username": "admin", "password": "admin123"}).json()["access_token"]
    resp = client.get("/api/meetings", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
