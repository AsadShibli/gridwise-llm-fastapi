"""Payload helpers and login-gated console pages."""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from console.models import OptimizationRun
from console.payload import clean_notes, load_default_profile, parse_full_json


class PayloadTests(SimpleTestCase):
    def test_clean_notes_drops_blanks(self):
        self.assertEqual(clean_notes("a", "  ", "b"), ["a", "b"])

    def test_parse_full_json_requires_keys(self):
        with self.assertRaises(ValueError):
            parse_full_json("{}")

    def test_parse_full_json_ok(self):
        body = parse_full_json(
            '{"scenario_id":"X","operator_notes":["n"],"hours":[],"battery":{}}'
        )
        self.assertEqual(body["scenario_id"], "X")

    def test_default_profile_has_24_hours(self):
        profile = load_default_profile()
        self.assertEqual(len(profile["hours"]), 24)
        self.assertIn("capacity_kwh", profile["battery"])


class SubmitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ada", password="test-pass-123")
        self.client.login(username="ada", password="test-pass-123")

    @patch("console.views.post_optimize_energy")
    def test_submit_notes_saves_success_run(self, mock_post):
        mock_post.return_value = (
            200,
            {
                "scenario_id": "CONSOLE-01",
                "directive_interpretation": [],
                "hourly_plan": [],
                "total_grid_kwh": 1.0,
                "total_cost_bdt": 2.0,
                "peak_grid_kwh": 3.0,
                "plan_summary": "ok",
            },
        )
        response = self.client.post(
            "/runs/new/",
            {"scenario_id": "CONSOLE-01", "note_1": "Do not charge from 1 PM to 3 PM."},
        )
        self.assertEqual(response.status_code, 302)
        run = OptimizationRun.objects.get(user=self.user)
        self.assertEqual(run.status, OptimizationRun.STATUS_SUCCESS)
        self.assertEqual(run.total_cost_bdt, 2.0)

    def test_other_users_run_is_404(self):
        other = User.objects.create_user("bob", password="test-pass-123")
        run = OptimizationRun.objects.create(
            user=other,
            scenario_id="SECRET",
            operator_notes=["x"],
            request_payload={},
            status=OptimizationRun.STATUS_ERROR,
        )
        response = self.client.get(f"/runs/{run.pk}/")
        self.assertEqual(response.status_code, 404)

