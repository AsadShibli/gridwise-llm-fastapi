"""FastAPI entrypoint: /health and the full optimize-energy pipeline."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.guardrails import validate_all
from app.llm_interpreter import interpret_notes
from app.optimizer import build_and_solve
from app.replay import compute_totals, make_plan_summary, replay_and_check
from app.schemas import OptimizeRequest, OptimizeResponse

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="GridWise LLM")

# Browser console at "/" (judge routes below are unchanged).
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def console() -> FileResponse:
    """Serve the single-page GridWise console."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    """Judges poll this; must return 200 with status ok."""
    return {"status": "ok"}


@app.post("/optimize-energy")
def optimize_energy(request: OptimizeRequest) -> OptimizeResponse:
    """LLM notes -> guardrails -> LP -> replay -> JSON response."""
    # Stub idle-grid plan removed: the real pipeline below returns the schedule.
    raw = interpret_notes(request.operator_notes)
    trusted = validate_all(raw, request.battery, len(request.operator_notes))
    plan = build_and_solve(request.hours, request.battery, trusted)
    replay_and_check(plan, request.hours, request.battery, trusted)
    total_grid, total_cost, peak = compute_totals(plan, request.hours)
    return OptimizeResponse(
        scenario_id=request.scenario_id,
        directive_interpretation=trusted,
        hourly_plan=plan,
        total_grid_kwh=total_grid,
        total_cost_bdt=total_cost,
        peak_grid_kwh=peak,
        plan_summary=make_plan_summary(trusted),
    )
