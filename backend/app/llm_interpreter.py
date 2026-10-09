"""Turn operator notes into structured directives via one LLM JSON call."""

import json
import logging

import httpx

from app import config

logger = logging.getLogger(__name__)

# The model sees the notes and battery capacity only, never demand/solar/tariff numbers.
SYSTEM_PROMPT = """You interpret campus operator notes into energy-schedule directives.
Return ONLY JSON: {"directives":[...]} with one object per note, in note_index order.

Each object: note_index (int), applies (bool), directive_type, structured_adjustment, explanation.

directive_type must be one of:
- solar_reduction: usable solar drops. structured_adjustment {"hours":[int], "factor": number}
  factor is the fraction REMAINING (80% reduction => factor 0.2; "25% of forecast" => 0.25).
- minimum_battery_reserve: battery SOC must stay >= X kWh. {"hours":[int], "minimum_energy_kwh": number}
  minimum_energy_kwh is always in kWh: convert "N% of capacity" using the given battery capacity.
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


def _user_prompt(operator_notes: list[str], capacity_kwh: float) -> str:
    """Numbered notes plus battery capacity (for "% of capacity" reserves)."""
    lines = [f"Battery capacity: {capacity_kwh:g} kWh.", "Interpret these operator notes:", ""]
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


GROQ_URL = "https://api.groq.com/openai/v1"


# (name, base_url, api_key, model). All expose an OpenAI-compatible API.
# Groq rate limits are per model, so a second Groq model absorbs bursts.
def _providers() -> list[tuple[str, str, str, str]]:
    return [
        ("groq", GROQ_URL, config.GROQ_API_KEY, config.GROQ_MODEL),
        ("groq-fallback", GROQ_URL, config.GROQ_API_KEY, config.GROQ_FALLBACK_MODEL),
        ("openrouter", "https://openrouter.ai/api/v1", config.OPENROUTER_API_KEY, config.OPENROUTER_MODEL),
        (
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            config.GEMINI_API_KEY,
            config.GEMINI_MODEL,
        ),
    ]


def _call_chat(base_url: str, api_key: str, model: str, operator_notes: list[str], capacity_kwh: float) -> list[dict]:
    """POST /chat/completions in JSON mode and parse the directives list."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(operator_notes, capacity_kwh)},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{base_url}/chat/completions"
    with httpx.Client(timeout=config.LLM_TIMEOUT_SECONDS) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    return _parse_directives(content)


def interpret_notes(operator_notes: list[str], capacity_kwh: float) -> list[dict]:
    """Try each configured provider in order; an empty list means all notes become no_op."""
    for name, base_url, api_key, model in _providers():
        if not api_key:
            continue
        try:
            directives = _call_chat(base_url, api_key, model, operator_notes, capacity_kwh)
            logger.info("LLM %s returned %s directives", name, len(directives))
            return directives
        except Exception as exc:  # keep serving even if a provider is down
            logger.warning("LLM %s failed: %s", name, type(exc).__name__)
    logger.warning("No LLM provider succeeded; guardrails will mark notes as no_op")
    return []
