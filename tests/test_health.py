from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_hash_api_key_is_sha256_hex() -> None:
    from app.security import hash_api_key

    digest = hash_api_key("sk_example")
    assert len(digest) == 64
    assert digest == hash_api_key("sk_example")
    assert digest != hash_api_key("sk_other")
