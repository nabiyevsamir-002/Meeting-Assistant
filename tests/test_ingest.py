"""Bilik bazası yükləmə/əvəzləmə testləri.

Əsas ssenari (düzəldilən bug): yeni sənəd yüklənəndə KÖHNƏ sənəd bazadan
silinməli, yeni suallara qarışmamalıdır (əvvəl köhnə Nexora yeni OpenAI
suallarına cavab verirdi).
"""


def _upload(client, name: str, content: str, replace: bool = True):
    url = f"/api/ingest/file?replace={'true' if replace else 'false'}"
    return client.post(url, files={"file": (name, content.encode(), "text/plain")})


def test_new_upload_replaces_old_knowledge_base(client):
    # 1) Köhnə sənəd (Nexora) yüklənir və axtarışda görünür
    assert _upload(client, "nexora.txt",
                   "Nexora layihəsi komissiya beş faiz çatdırılma üç gün satış").status_code == 200
    hits = client.get("/api/ingest/search", params={"q": "komissiya", "top_k": 4}).json()
    assert any("nexora" in (h.get("title") or "").lower() for h in hits)

    # 2) Yeni sənəd (OpenAI) — replace default=true → köhnə tam silinir
    assert _upload(client, "openai.txt",
                   "OpenAI was founded in 2015 GPT models API pricing tokens").status_code == 200

    # 3) Köhnə Nexora artıq axtarış nəticələrində YOXDUR (qarışma bitdi)
    hits2 = client.get("/api/ingest/search", params={"q": "komissiya", "top_k": 4}).json()
    titles = {(h.get("title") or "").lower() for h in hits2}
    assert "nexora.txt" not in titles
    docs = {d["title"] for d in client.get("/api/ingest/documents").json()}
    assert docs == {"openai.txt"}


def test_append_upload_keeps_previous(client):
    # Sənəd + FAQ birlikdə: birincisi əvəzləyir, ikincisi replace=false ilə əlavə olunur
    assert _upload(client, "doc.txt", "Layihə sənədi əsas məzmun mətni").status_code == 200
    assert _upload(client, "faq.txt", "Tez-tez soruşulan suallar bölməsi",
                   replace=False).status_code == 200
    titles = {d["title"] for d in client.get("/api/ingest/documents").json()}
    assert {"doc.txt", "faq.txt"} <= titles


def test_clear_documents_endpoint(client):
    assert _upload(client, "x.txt", "silinəcək məzmun mətni burada").status_code == 200
    r = client.delete("/api/ingest/documents")
    assert r.status_code == 200
    assert r.json()["cleared"] >= 1
    assert client.get("/api/ingest/documents").json() == []
