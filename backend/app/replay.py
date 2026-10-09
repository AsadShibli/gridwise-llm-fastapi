"""Replay hourly_plan against energy rules and trusted directives."""

from app.optimizer import _effective_solar, _hour_set, _max_grid_caps, _min_reserve
from app.schemas import Battery, HourInput, HourlyPlanRow

TOL = 0.01  # official numeric tolerance in kWh / BDT


def _charge_discharge(row: HourlyPlanRow) -> tuple[float, float]:
    """Map battery_action + battery_kwh into charge and discharge kWh."""
    if row.battery_action == "charge":
        return row.battery_kwh, 0.0
    if row.battery_action == "discharge":
        return 0.0, row.battery_kwh
    return 0.0, 0.0


def compute_totals(plan: list[HourlyPlanRow], hours: list[HourInput]) -> tuple[float, float, float]:
    """Totals always come from the plan, never from a parallel running sum."""
    hours = sorted(hours, key=lambda item: item.hour)
    plan = sorted(plan, key=lambda row: row.hour)
    total_grid = sum(row.grid_kwh for row in plan)
    total_cost = sum(
        row.grid_kwh * hours[row.hour].tariff_bdt_per_kwh for row in plan
    )
    peak = max(row.grid_kwh for row in plan)
    return total_grid, total_cost, peak


def make_plan_summary(directives: list[dict]) -> str:
    """Short free-text summary; wording does not need to match samples."""
    applied = [d["directive_type"] for d in directives if d.get("applies")]
    if not applied:
        return "No operator directives applied; schedule minimizes grid electricity cost."
    return "Applied " + ", ".join(applied) + " and minimized grid electricity cost."


def replay_and_check(
    plan: list[HourlyPlanRow],
    hours: list[HourInput],
    battery: Battery,
    directives: list[dict],
) -> None:
    """Raise ValueError if the plan would fail the judge's self-replay."""
    hours = sorted(hours, key=lambda item: item.hour)
    plan = sorted(plan, key=lambda row: row.hour)
    if [row.hour for row in plan] != list(range(24)):
        raise ValueError("hourly_plan must cover hours 0-23 once")
    solar = _effective_solar(hours, directives)
    floors = _min_reserve(hours, battery, directives)
    no_charge = _hour_set(directives, "no_charge_window")
    no_discharge = _hour_set(directives, "no_discharge_window")
    grid_caps = _max_grid_caps(directives)
    energy = battery.initial_energy_kwh
    for h, row in enumerate(plan):
        charge_kwh, discharge_kwh = _charge_discharge(row)
        _check_hour(
            h, row, hours[h], battery, solar[h], floors[h],
            charge_kwh, discharge_kwh, energy,
            no_charge, no_discharge, grid_caps,
        )
        energy = energy + charge_kwh - discharge_kwh
        if abs(energy - row.battery_energy_after_kwh) > TOL:
            raise ValueError(f"hour {h}: battery_energy_after_kwh mismatch")
    if abs(energy - battery.initial_energy_kwh) > TOL:
        raise ValueError("end-of-day battery must equal initial_energy_kwh")


def _check_hour(
    h,
    row,
    hour,
    battery,
    effective_solar,
    floor,
    charge_kwh,
    discharge_kwh,
    energy_before,
    no_charge,
    no_discharge,
    grid_caps,
) -> None:
    """One hour: energy balance, solar cap, rates, SOC bounds, directives."""
    left = row.grid_kwh + row.solar_used_kwh + discharge_kwh
    right = hour.demand_kwh + charge_kwh
    if abs(left - right) > TOL:
        raise ValueError(f"hour {h}: energy balance failed")
    if row.solar_used_kwh - effective_solar > TOL:
        raise ValueError(f"hour {h}: solar_used exceeds effective solar")
    if row.battery_action == "idle" and row.battery_kwh > TOL:
        raise ValueError(f"hour {h}: idle requires battery_kwh 0")
    if charge_kwh - battery.max_charge_kwh_per_hour > TOL:
        raise ValueError(f"hour {h}: charge rate exceeded")
    if discharge_kwh - battery.max_discharge_kwh_per_hour > TOL:
        raise ValueError(f"hour {h}: discharge rate exceeded")
    if h in no_charge and charge_kwh > TOL:
        raise ValueError(f"hour {h}: charge forbidden")
    if h in no_discharge and discharge_kwh > TOL:
        raise ValueError(f"hour {h}: discharge forbidden")
    if h in grid_caps and row.grid_kwh - grid_caps[h] > TOL:
        raise ValueError(f"hour {h}: grid cap exceeded")
    energy_after = energy_before + charge_kwh - discharge_kwh
    if energy_after + TOL < floor or energy_after - TOL > battery.capacity_kwh:
        raise ValueError(f"hour {h}: battery energy outside bounds")
