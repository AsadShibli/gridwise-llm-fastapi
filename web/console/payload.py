"""Build a FastAPI OptimizeRequest dict from the Django form."""

import json
import os
from pathlib import Path
from typing import Any

# web/console/payload.py -> repo root (sample.json lives next to app/).
REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_KEYS = {"scenario_id", "operator_notes", "hours", "battery"}


def sample_json_path() -> Path:
    """Compose can point this at a copied sample.json via SAMPLE_JSON_PATH."""
    override = os.getenv("SAMPLE_JSON_PATH", "").strip()
    if override:
        return Path(override)
    return REPO_ROOT / "sample.json"


def load_default_profile() -> dict[str, Any]:
    """Hours + battery from the public sample file (not operator notes)."""
    data = json.loads(sample_json_path().read_text(encoding="utf-8"))
    return {"hours": data["hours"], "battery": data["battery"]}


def clean_notes(note_1: str, note_2: str, note_3: str) -> list[str]:
    return [n.strip() for n in (note_1, note_2, note_3) if n and n.strip()]


def parse_full_json(raw: str) -> dict[str, Any]:
    """Parse a pasted/uploaded body; require the four FastAPI top-level keys."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    missing = REQUIRED_KEYS - set(data)
    if missing:
        raise ValueError(f"JSON missing keys: {sorted(missing)}")
    return data
