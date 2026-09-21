"""Turn operator notes into structured directives via one LLM JSON call."""

import json
import logging

import httpx

from app import config

logger = logging.getLogger(__name__)

# The model only sees notes, never demand/solar/tariff numbers.
SYSTEM_PROMPT = """You interpret campus operator notes into energy-schedule directives.
Return ONLY JSON: {"directives":[...]} with one object per note, in note_index order.

Each object: note_index (int), applies (bool), directive_type, structured_adjustment, explanation.

directive_type must be one of:
- solar_reduction: usable solar drops. structured_adjustment {"hours":[int], "factor": number}
  factor is the fraction REMAINING (80% reduction => factor 0.2; "25% of forecast" => 0.25).
- minimum_battery_reserve: battery SOC must stay >= X kWh. {"hours":[int], "minimum_energy_kwh": number}
- no_charge_window: battery may not charge. {"hours":[int]}
- no_discharge_window: battery may not discharge. {"hours":[int]}
- max_grid_window: grid import capped. {"hours":[int], "max_grid_kwh": number}
- no_op: distractor that does not affect today's 24-hour schedule.
  applies=false and structured_adjustment=null.

Hours are start-inclusive and end-exclusive on a 0-23 clock.
"1 PM to 3 PM" => [13, 14] (not 15). "noon until 2 PM" => [12, 13].
"from 2 AM to 5 AM" => [2, 3, 4]. Hours must be unique integers 0-23, ascending.

Ignore notes about other days, other sites, sports, deadlines, or anything that
does not change today's battery/solar/grid schedule. Those are no_op.

Examples:
Note: "Wash rooftop panels noon until 2 PM; usable solar is 25% of forecast."
-> solar_reduction, hours [12,13], factor 0.25, applies true
Note: "Sports office moved next month's registration deadline."
-> no_op, applies false, structured_adjustment null
Note: "An 80% solar reduction from 10 AM to noon."
-> solar_reduction, hours [10,11], factor 0.2
"""


def _user_prompt(operator_notes: list[str]) -> str:
    """Numbered notes only — no energy numbers for the model to copy."""
    lines = ["Interpret these operator notes:", ""]
    for index, note in enumerate(operator_notes):
        lines.append(f"{index}: {note}")
    lines.append("")
    lines.append("Return JSON {\"directives\": [...]} with one entry per note.")
    return "\n".join(lines)


def _parse_directives(text: str) -> list[dict]:
    """Parse model JSON into a list of directive dicts."""
    cleaned = text.strip()
    # Strip markdown fences if the model wraps JSON anyway.
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    data = json.loads(cleaned)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("directives"), list):
            return data["directives"]
        # Some models wrap a single object; accept that too.
        if "note_index" in data or "directive_type" in data:
            return [data]
    raise ValueError("LLM JSON did not contain a directives list")


def _call_openai_chat(
    base_url: str,
    api_key: str,
    model: str,
    operator_notes: list[str],
    json_mode: bool = True,
) -> list[dict]:
    """POST /chat/completions (OpenAI-compatible) and parse directives JSON."""
    if not base_url:
        raise RuntimeError("OpenAI-compatible base URL is missing")
    if not api_key:
        raise RuntimeError("OpenAI-compatible API key is missing")
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(operator_notes)},
        ],
        "temperature": 0,
    }
    # Groq/OpenRouter honor json_object; some proxies only need the prompt.
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = base_url.rstrip("/") + "/chat/completions"
    with httpx.Client(timeout=config.LLM_TIMEOUT_SECONDS) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    return _parse_directives(content)


def _call_free_ai_gateway(operator_notes: list[str]) -> list[dict]:
    """Optional local/remote Free-AI Gateway (capability-routed proxy)."""
    if not config.FREE_AI_GATEWAY_URL:
        raise RuntimeError("FREE_AI_GATEWAY_URL is missing")
    return _call_openai_chat(
        config.FREE_AI_GATEWAY_URL,
        config.FREE_AI_GATEWAY_API_KEY or "not-needed",
        "auto:structured_output",
        operator_notes,
        json_mode=False,
    )


def _call_groq(operator_notes: list[str]) -> list[dict]:
    """Groq OpenAI-compatible chat; works without a Node gateway process."""
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing")
    return _call_openai_chat(
        "https://api.groq.com/openai/v1",
        config.GROQ_API_KEY,
        config.GROQ_MODEL,
        operator_notes,
        json_mode=True,
    )


def _call_openrouter(operator_notes: list[str]) -> list[dict]:
    """Primary provider: OpenRouter chat completions with JSON mode."""
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is missing")
    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(operator_notes)},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=config.LLM_TIMEOUT_SECONDS) as client:
        response = client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    return _parse_directives(content)


def _call_gemini(operator_notes: list[str]) -> list[dict]:
    """Fallback provider: Gemini generateContent with JSON MIME type."""
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.GEMINI_MODEL}:generateContent"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": SYSTEM_PROMPT + "\n\n" + _user_prompt(operator_notes)}
                ]
            }
        ],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    with httpx.Client(timeout=config.LLM_TIMEOUT_SECONDS) as client:
        response = client.post(
            url,
            params={"key": config.GEMINI_API_KEY},
            json=payload,
        )
        response.raise_for_status()
        content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_directives(content)


def interpret_notes(operator_notes: list[str]) -> list[dict]:
    """Gateway, Groq, OpenRouter (retry), Gemini; empty list means all no_op."""
    attempts = [
        ("free-ai-gateway", _call_free_ai_gateway),
        ("groq", _call_groq),
        ("openrouter", _call_openrouter),
        ("openrouter-retry", _call_openrouter),
        ("gemini", _call_gemini),
    ]
    for label, caller in attempts:
        try:
            directives = caller(operator_notes)
            logger.info("LLM %s returned %s directives", label, len(directives))
            return directives
        except Exception as exc:  # keep serving even if a provider is down
            logger.warning("LLM %s failed: %s", label, type(exc).__name__)
    logger.warning("All LLM providers failed; guardrails will mark notes as no_op")
    return []
