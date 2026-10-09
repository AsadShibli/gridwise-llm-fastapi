"""Pydantic request and response models matching the judge JSON contract."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Allowed directive types from the problem statement.
DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]

# battery_action is a single value per hour (never charge and discharge).
BatteryAction = Literal["charge", "discharge", "idle"]


class HourInput(BaseModel):
    """One hour of campus demand, solar forecast, and grid tariff."""

    hour: int = Field(..., ge=0, le=23)
    demand_kwh: float = Field(..., ge=0)
    solar_kwh: float = Field(..., ge=0)
    tariff_bdt_per_kwh: float = Field(..., ge=0)


class Battery(BaseModel):
    """Battery hardware limits used by the optimizer and replay check."""

    capacity_kwh: float = Field(..., gt=0)
    initial_energy_kwh: float = Field(..., ge=0)
    minimum_energy_kwh: float = Field(..., ge=0)
    max_charge_kwh_per_hour: float = Field(..., ge=0)
    max_discharge_kwh_per_hour: float = Field(..., ge=0)


class OptimizeRequest(BaseModel):
    """POST /optimize-energy body: energy data plus 1–3 operator notes."""

    scenario_id: str = Field(..., min_length=1)
    operator_notes: list[str] = Field(..., min_length=1, max_length=3)
    hours: list[HourInput]
    battery: Battery

    @field_validator("operator_notes")
    @classmethod
    def notes_must_be_nonempty(cls, notes: list[str]) -> list[str]:
        # Empty strings are not valid operator notes.
        if any(not note.strip() for note in notes):
            raise ValueError("operator_notes must be non-empty strings")
        return notes

    @field_validator("hours")
    @classmethod
    def hours_must_cover_full_day(cls, hours: list[HourInput]) -> list[HourInput]:
        # Judges require exactly hours 0..23, each once.
        if len(hours) != 24:
            raise ValueError("hours must contain exactly 24 entries")
        values = sorted(item.hour for item in hours)
        if values != list(range(24)):
            raise ValueError("hours must be unique integers 0 through 23")
        return hours


class DirectiveInterpretation(BaseModel):
    """One LLM note mapped to a structured directive (or no_op)."""

    note_index: int = Field(..., ge=0, le=2)
    applies: bool
    directive_type: DirectiveType
    # Shape depends on directive_type; guardrails check it before the LP.
    structured_adjustment: Optional[dict[str, Any]] = None
    explanation: str


class HourlyPlanRow(BaseModel):
    """One hour of the returned battery/grid/solar schedule."""

    hour: int = Field(..., ge=0, le=23)
    grid_kwh: float = Field(..., ge=0)
    solar_used_kwh: float = Field(..., ge=0)
    battery_action: BatteryAction
    battery_kwh: float = Field(..., ge=0)
    battery_energy_after_kwh: float = Field(..., ge=0)


class OptimizeResponse(BaseModel):
    """POST /optimize-energy response body."""

    scenario_id: str
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanRow]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str
