"""Linear program: minimize grid cost subject to battery and directive rules."""

import pulp

from app.schemas import Battery, HourInput, HourlyPlanRow

EPS = 1e-6  # treat tiny charge/discharge as idle


def _hours_for(directive: dict) -> list[int]:
    adj = directive.get("structured_adjustment") or {}
    return list(adj.get("hours") or [])


def _effective_solar(hours: list[HourInput], directives: list[dict]) -> list[float]:
    """Apply solar_reduction factors (fraction remaining) per hour."""
    solar = [item.solar_kwh for item in hours]
    for directive in directives:
        if not directive.get("applies"):
            continue
        if directive.get("directive_type") != "solar_reduction":
            continue
        factor = float(directive["structured_adjustment"]["factor"])
        for hour in _hours_for(directive):
            solar[hour] *= factor
    return solar


def _min_reserve(hours: list[HourInput], battery: Battery, directives: list[dict]) -> list[float]:
    """Per-hour SOC floor: hardware minimum, raised by reserve directives."""
    floors = [battery.minimum_energy_kwh] * 24
    for directive in directives:
        if not directive.get("applies"):
            continue
        if directive.get("directive_type") != "minimum_battery_reserve":
            continue
        extra = float(directive["structured_adjustment"]["minimum_energy_kwh"])
        for hour in _hours_for(directive):
            floors[hour] = max(floors[hour], extra)
    return floors


def _hour_set(directives: list[dict], directive_type: str) -> set[int]:
    hours: set[int] = set()
    for directive in directives:
        if directive.get("applies") and directive.get("directive_type") == directive_type:
            hours.update(_hours_for(directive))
    return hours


def _max_grid_caps(directives: list[dict]) -> dict[int, float]:
    caps: dict[int, float] = {}
    for directive in directives:
        if not directive.get("applies"):
            continue
        if directive.get("directive_type") != "max_grid_window":
            continue
        cap = float(directive["structured_adjustment"]["max_grid_kwh"])
        for hour in _hours_for(directive):
            caps[hour] = cap if hour not in caps else min(caps[hour], cap)
    return caps


def _idle_grid_plan(hours: list[HourInput], battery: Battery) -> list[HourlyPlanRow]:
    """Fallback if CBC finds no optimum: idle battery, demand from grid."""
    initial = battery.initial_energy_kwh
    return [
        HourlyPlanRow(
            hour=item.hour,
            grid_kwh=item.demand_kwh,
            solar_used_kwh=0.0,
            battery_action="idle",
            battery_kwh=0.0,
            battery_energy_after_kwh=initial,
        )
        for item in hours
    ]


def build_and_solve(
    hours: list[HourInput],
    battery: Battery,
    directives: list[dict],
) -> list[HourlyPlanRow]:
    """Solve the 24-hour LP and return a normalized hourly_plan."""
    hours = sorted(hours, key=lambda item: item.hour)
    solar = _effective_solar(hours, directives)
    floors = _min_reserve(hours, battery, directives)
    no_charge = _hour_set(directives, "no_charge_window")
    no_discharge = _hour_set(directives, "no_discharge_window")
    grid_caps = _max_grid_caps(directives)

    problem = pulp.LpProblem("gridwise", pulp.LpMinimize)
    grid = [pulp.LpVariable(f"grid_{h}", lowBound=0) for h in range(24)]
    solar_used = [
        pulp.LpVariable(f"solar_{h}", lowBound=0, upBound=solar[h]) for h in range(24)
    ]
    charge = [pulp.LpVariable(f"charge_{h}", lowBound=0) for h in range(24)]
    discharge = [pulp.LpVariable(f"discharge_{h}", lowBound=0) for h in range(24)]
    soc = [
        pulp.LpVariable(f"soc_{h}", lowBound=floors[h], upBound=battery.capacity_kwh)
        for h in range(24)
    ]

    problem += pulp.lpSum(grid[h] * hours[h].tariff_bdt_per_kwh for h in range(24))
    _add_hourly_constraints(
        problem, hours, battery, grid, solar_used, charge, discharge, soc,
        no_charge, no_discharge, grid_caps,
    )
    status = problem.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=10))
    if pulp.LpStatus[status] != "Optimal":
        return _idle_grid_plan(hours, battery)
    return _normalize_plan(hours, grid, solar_used, charge, discharge, soc)


def _add_hourly_constraints(
    problem,
    hours,
    battery,
    grid,
    solar_used,
    charge,
    discharge,
    soc,
    no_charge,
    no_discharge,
    grid_caps,
) -> None:
    """Energy balance, rates, directive windows, and end-of-day neutrality."""
    for h in range(24):
        # grid + solar + discharge = demand + charge
        problem += (
            grid[h] + solar_used[h] + discharge[h] == hours[h].demand_kwh + charge[h]
        )
        max_c = 0 if h in no_charge else battery.max_charge_kwh_per_hour
        max_d = 0 if h in no_discharge else battery.max_discharge_kwh_per_hour
        problem += charge[h] <= max_c
        problem += discharge[h] <= max_d
        if h in grid_caps:
            problem += grid[h] <= grid_caps[h]
        prev = battery.initial_energy_kwh if h == 0 else soc[h - 1]
        problem += soc[h] == prev + charge[h] - discharge[h]
    # End of hour 23 must restore the starting battery energy.
    problem += soc[23] == battery.initial_energy_kwh


def _normalize_plan(hours, grid, solar_used, charge, discharge, soc) -> list[HourlyPlanRow]:
    """One battery_action per hour; never report simultaneous charge and discharge."""
    rows = []
    for h in range(24):
        net = float(pulp.value(charge[h]) or 0.0) - float(pulp.value(discharge[h]) or 0.0)
        if net > EPS:
            action, battery_kwh = "charge", net
        elif net < -EPS:
            action, battery_kwh = "discharge", -net
        else:
            action, battery_kwh = "idle", 0.0
        rows.append(
            HourlyPlanRow(
                hour=h,
                grid_kwh=max(0.0, float(pulp.value(grid[h]) or 0.0)),
                solar_used_kwh=max(0.0, float(pulp.value(solar_used[h]) or 0.0)),
                battery_action=action,
                battery_kwh=battery_kwh,
                battery_energy_after_kwh=float(pulp.value(soc[h]) or 0.0),
            )
        )
    return rows
