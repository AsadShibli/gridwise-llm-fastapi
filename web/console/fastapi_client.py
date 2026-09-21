"""Server-side call to the existing FastAPI optimizer (no browser CORS)."""

from typing import Any

import httpx
from django.conf import settings


def post_optimize_energy(body: dict[str, Any]) -> tuple[int, Any]:
    """POST /optimize-energy. Returns (status_code, json_or_error_text)."""
    url = f"{settings.FASTAPI_URL}/optimize-energy"
    try:
        # Judge budget is 30s; keep Django's wait aligned.
        response = httpx.post(url, json=body, timeout=30.0)
    except httpx.HTTPError as exc:
        return 0, str(exc)
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, response.text
