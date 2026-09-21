"""History, new-run submit, and owned-run detail."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from console.fastapi_client import post_optimize_energy
from console.forms import RunForm
from console.models import OptimizationRun
from console.payload import clean_notes, load_default_profile, parse_full_json


@login_required
def run_list(request):
    runs = OptimizationRun.objects.filter(user=request.user)
    return render(request, "console/run_list.html", {"runs": runs})


@login_required
def run_detail(request, pk: int):
    # 404 if another user owns the row.
    run = get_object_or_404(OptimizationRun, pk=pk, user=request.user)
    return render(request, "console/run_detail.html", {"run": run})


def _read_optional_json(form: RunForm) -> str:
    raw = (form.cleaned_data.get("json_text") or "").strip()
    upload = form.cleaned_data.get("json_file")
    if upload:
        raw = upload.read().decode("utf-8")
    return raw


def _build_body(form: RunForm) -> dict:
    notes = clean_notes(
        form.cleaned_data.get("note_1") or "",
        form.cleaned_data.get("note_2") or "",
        form.cleaned_data.get("note_3") or "",
    )
    raw = _read_optional_json(form)
    if raw:
        body = parse_full_json(raw)
        if notes:
            body["operator_notes"] = notes
        body["scenario_id"] = form.cleaned_data["scenario_id"]
        return body
    profile = load_default_profile()
    return {
        "scenario_id": form.cleaned_data["scenario_id"],
        "operator_notes": notes,
        "hours": profile["hours"],
        "battery": profile["battery"],
    }


@login_required
def run_new(request):
    form = RunForm(request.POST or None, request.FILES or None)
    if request.method != "POST" or not form.is_valid():
        return render(request, "console/run_new.html", {"form": form})
    try:
        body = _build_body(form)
        notes = body["operator_notes"]
        if not (1 <= len(notes) <= 3):
            raise ValueError("Need 1–3 non-empty operator notes.")
    except (ValueError, UnicodeDecodeError) as exc:
        form.add_error(None, str(exc))
        return render(request, "console/run_new.html", {"form": form})

    status_code, payload = post_optimize_energy(body)
    run = OptimizationRun(
        user=request.user,
        scenario_id=body["scenario_id"],
        operator_notes=notes,
        request_payload=body,
    )
    if status_code == 200 and isinstance(payload, dict):
        run.status = OptimizationRun.STATUS_SUCCESS
        run.response_payload = payload
        run.total_cost_bdt = payload.get("total_cost_bdt")
        run.total_grid_kwh = payload.get("total_grid_kwh")
        run.peak_grid_kwh = payload.get("peak_grid_kwh")
        messages.success(request, "Optimization finished.")
    else:
        run.status = OptimizationRun.STATUS_ERROR
        run.error_message = f"HTTP {status_code}: {payload}"
        messages.error(request, "FastAPI call failed; see this run for details.")
    run.save()
    return redirect("run_detail", pk=run.pk)
