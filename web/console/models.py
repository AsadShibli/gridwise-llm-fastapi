"""One stored optimize-energy call per row (request + response + totals)."""

from django.conf import settings
from django.db import models


class OptimizationRun(models.Model):
    """A logged-in user's FastAPI optimize-energy attempt."""

    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_SUCCESS, "Success"),
        (STATUS_ERROR, "Error"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    scenario_id = models.CharField(max_length=128)
    operator_notes = models.JSONField()
    request_payload = models.JSONField()
    response_payload = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    error_message = models.TextField(blank=True)
    total_cost_bdt = models.FloatField(null=True, blank=True)
    total_grid_kwh = models.FloatField(null=True, blank=True)
    peak_grid_kwh = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.scenario_id} ({self.status})"
