"""Confirm GET /health matches the required contract."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


if __name__ == "__main__":
    test_health()
    print("health ok")
