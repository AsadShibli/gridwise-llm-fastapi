"""FastAPI entrypoint: /health and the full optimize-energy pipeline."""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.guardrails import validate_all
from app.llm_interpreter import interpret_notes
from app.optimizer import NoFeasibleSchedule, build_and_solve
from app.replay import compute_totals, make_plan_summary, replay_and_check
from app.schemas import OptimizeRequest, OptimizeResponse

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="GridWise LLM",
    description="Operator notes -> LLM directives -> guardrails -> LP schedule -> replay check.",
)

# Public demo API: the static frontend (another origin) calls it from the browser.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


@app.exception_handler(ValueError)
def replay_failed(request: Request, exc: ValueError) -> JSONResponse:
    """A plan that fails self-replay is a server bug; answer with JSON (and CORS headers)."""
    return JSONResponse(status_code=500, content={"detail": f"Schedule failed replay check: {exc}"})


@app.get("/", include_in_schema=False)
def index() -> dict:
    """Small landing payload so the bare API URL is not a 404."""
    return {"name": "GridWise LLM API", "docs": "/docs", "health": "/health", "optimize": "POST /optimize-energy"}


@app.get("/health")
def health() -> dict:
    """Judges poll this; must return 200 with status ok."""
    return {"status": "ok"}


@app.post("/optimize-energy")
def optimize_energy(request: OptimizeRequest) -> OptimizeResponse:
    """LLM notes -> guardrails -> LP -> replay -> JSON response."""
    raw = interpret_notes(request.operator_notes, request.battery.capacity_kwh)
    trusted = validate_all(raw, request.battery, len(request.operator_notes))
    try:
        plan = build_and_solve(request.hours, request.battery, trusted)
    except NoFeasibleSchedule:
        applied = ", ".join(d["directive_type"] for d in trusted if d["applies"]) or "none"
        raise HTTPException(
            status_code=422,
            detail=f"No valid schedule exists: the directives ({applied}) cannot all be met with this battery and demand.",
        )
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
