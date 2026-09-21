"""Run all public samples through the optimizer using reference directives."""

import json
from pathlib import Path

from app.optimizer import build_and_solve
from app.replay import compute_totals, replay_and_check
from app.schemas import OptimizeRequest

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
TOL = 0.01


def test_optimizer_matches_sample_costs() -> None:
    pack = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    for case in pack["cases"]:
        request = OptimizeRequest.model_validate(case["input"])
        directives = case["expected_output"]["directive_interpretation"]
        plan = build_and_solve(request.hours, request.battery, directives)
        replay_and_check(plan, request.hours, request.battery, directives)
        _, total_cost, _ = compute_totals(plan, request.hours)
        expected = case["expected_output"]["total_cost_bdt"]
        # LP should match (or beat) the public reference optimum.
        assert total_cost <= expected + TOL, f"{case['id']}: {total_cost} > {expected}"
        print(case["id"], "cost", round(total_cost, 4), "ref", expected)


if __name__ == "__main__":
    test_optimizer_matches_sample_costs()
    print("all public samples: optimizer + replay ok")
