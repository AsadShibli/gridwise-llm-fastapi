"""Auth pages send anonymous users to login."""

from django.test import TestCase


class AuthGateTests(TestCase):
    def test_history_redirects_when_logged_out(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])
