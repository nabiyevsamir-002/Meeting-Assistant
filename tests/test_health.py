"""Sağlamlıq endpointinin testi."""


def test_health_returns_ok_and_mock_providers(client):
    """Açarsız mühitdə /health bütün provayderləri mock göstərməlidir."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["providers"]["llm"] == "mock"
    assert data["providers"]["stt"] == "mock"
    assert data["providers"]["vector_store"] == "memory"
