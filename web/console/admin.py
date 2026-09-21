from django.contrib import admin

from console.models import OptimizationRun


@admin.register(OptimizationRun)
class OptimizationRunAdmin(admin.ModelAdmin):
    """Staff can browse stored FastAPI calls (no LLM keys in these rows)."""

    list_display = (
        "id",
        "user",
        "scenario_id",
        "status",
        "total_cost_bdt",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("scenario_id", "user__username")
    readonly_fields = ("created_at",)
