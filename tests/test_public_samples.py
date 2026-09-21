"""POST SAMPLE-01 through the live app (LLM may fall back to no_op without keys)."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SAMPLE_PATH = Path(__file__).resolve().parents[1] / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"


def test_sample_01_returns_contract() -> None:
    payload = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))["cases"][0]["input"]
    response = client.post("/optimize-energy", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["scenario_id"] == payload["scenario_id"]
    assert len(body["directive_interpretation"]) == len(payload["operator_notes"])
    assert len(body["hourly_plan"]) == 24
    assert "total_grid_kwh" in body and "plan_summary" in body


def test_four_notes_rejected() -> None:
    payload = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))["cases"][0]["input"]
    payload = dict(payload)
    payload["operator_notes"] = payload["operator_notes"] + ["extra", "too many"]
    response = client.post("/optimize-energy", json=payload)
    assert response.status_code == 422


if __name__ == "__main__":
    test_sample_01_returns_contract()
    test_four_notes_rejected()
    print("sample-01 contract ok")
