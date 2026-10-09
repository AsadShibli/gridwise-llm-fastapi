"""Guardrail unit checks: invalid LLM output becomes no_op."""

from app.guardrails import validate_all, validate_directive
from app.schemas import Battery

BATTERY = Battery(
    capacity_kwh=220,
    initial_energy_kwh=110,
    minimum_energy_kwh=40,
    max_charge_kwh_per_hour=50,
    max_discharge_kwh_per_hour=50,
)


def test_bad_type_becomes_no_op() -> None:
    result = validate_directive({"directive_type": "explode"}, 0, BATTERY)
    assert result["directive_type"] == "no_op"
    assert result["applies"] is False
    assert result["structured_adjustment"] is None


def test_fills_missing_notes() -> None:
    trusted = validate_all([], BATTERY, note_count=2)
    assert len(trusted) == 2
    assert trusted[0]["note_index"] == 0
    assert trusted[1]["note_index"] == 1
    assert all(item["directive_type"] == "no_op" for item in trusted)


if __name__ == "__main__":
    test_bad_type_becomes_no_op()
    test_fills_missing_notes()
    print("guardrails ok")
