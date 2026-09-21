"""Deterministic checks on LLM output. Invalid notes become no_op."""

from typing import Any

from app.schemas import Battery

ALLOWED_TYPES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}


def as_no_op(note_index: int, reason: str) -> dict:
    """Safe default: distractor that does not change the LP."""
    return {
        "note_index": note_index,
        "applies": False,
        "directive_type": "no_op",
        "structured_adjustment": None,
        "explanation": reason,
    }


def _clean_hours(raw: Any) -> list[int] | None:
    """Unique integers 0–23, sorted ascending. None if invalid/empty."""
    if not isinstance(raw, list) or not raw:
        return None
    try:
        hours = [int(value) for value in raw]
    except (TypeError, ValueError):
        return None
    if any(hour < 0 or hour > 23 for hour in hours):
        return None
    # Sort and drop duplicates so the optimizer gets a clean hour list.
    return sorted(set(hours))


def validate_directive(raw: dict, note_index: int, battery: Battery) -> dict:
    """Validate one LLM dict; return a trusted directive or no_op."""
    if not isinstance(raw, dict):
        return as_no_op(note_index, "Interpretation could not be validated.")
    dtype = raw.get("directive_type")
    if dtype not in ALLOWED_TYPES:
        return as_no_op(note_index, "Unsupported directive type; treated as no_op.")
    if dtype == "no_op":
        return as_no_op(note_index, str(raw.get("explanation") or "Note does not affect today's schedule."))
    adj = raw.get("structured_adjustment")
    if not isinstance(adj, dict):
        return as_no_op(note_index, "Missing structured_adjustment; treated as no_op.")
    hours = _clean_hours(adj.get("hours"))
    if hours is None:
        return as_no_op(note_index, "Invalid hour window; treated as no_op.")
    return _typed_adjustment(dtype, hours, adj, note_index, battery, raw)


def _typed_adjustment(
    dtype: str,
    hours: list[int],
    adj: dict,
    note_index: int,
    battery: Battery,
    raw: dict,
) -> dict:
    """Build the required structured_adjustment shape for a non-no_op type."""
    explanation = str(raw.get("explanation") or f"Applied {dtype} on hours {hours}.")
    payload: dict[str, Any] = {"hours": hours}
    try:
        if dtype == "solar_reduction":
            factor = float(adj["factor"])
            if not 0 <= factor <= 1:
                return as_no_op(note_index, "solar_reduction factor must be in [0, 1].")
            payload["factor"] = factor
        elif dtype == "minimum_battery_reserve":
            minimum = float(adj["minimum_energy_kwh"])
            if minimum < 0 or minimum > battery.capacity_kwh:
                return as_no_op(note_index, "minimum_energy_kwh is outside battery capacity.")
            payload["minimum_energy_kwh"] = minimum
        elif dtype == "max_grid_window":
            cap = float(adj["max_grid_kwh"])
            if cap < 0:
                return as_no_op(note_index, "max_grid_kwh must be >= 0.")
            payload["max_grid_kwh"] = cap
        elif dtype not in ("no_charge_window", "no_discharge_window"):
            return as_no_op(note_index, "Unsupported directive type; treated as no_op.")
    except (TypeError, ValueError, KeyError):
        return as_no_op(note_index, "Malformed structured_adjustment; treated as no_op.")
    return {
        "note_index": note_index,
        "applies": True,
        "directive_type": dtype,
        "structured_adjustment": payload,
        "explanation": explanation,
    }


def validate_all(raw_directives: list[dict], battery: Battery, note_count: int) -> list[dict]:
    """Exactly one trusted directive per operator note, in note_index order."""
    by_index: dict[int, dict] = {}
    for item in raw_directives:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("note_index"))
        except (TypeError, ValueError):
            continue
        if 0 <= index < note_count and index not in by_index:
            by_index[index] = validate_directive(item, index, battery)
    trusted = []
    for index in range(note_count):
        trusted.append(
            by_index.get(index, as_no_op(index, "Interpretation could not be validated."))
        )
    return trusted
