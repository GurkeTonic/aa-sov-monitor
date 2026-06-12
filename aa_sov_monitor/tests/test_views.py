"""Tests for views"""

from django.test import TestCase

from allianceauth.tests.auth_utils import AuthUtils


class TestIndexView(TestCase):
    def setUp(self):
        self.user_no_perm = AuthUtils.create_user("no_perm_user")
        self.user_with_perm = AuthUtils.create_user("perm_user")
        # Hook URLs are auto-wrapped with main_character_required, so the user
        # needs a main character to reach the view.
        AuthUtils.add_main_character_2(
            self.user_with_perm, "Perm Char", 90000010, corp_id=2001, corp_name="Test Corp"
        )
        AuthUtils.add_permission_to_user_by_name(
            "aa_sov_monitor.view_sov", self.user_with_perm
        )

    def test_index_redirects_without_permission(self):
        self.client.force_login(self.user_no_perm)
        response = self.client.get("/sov/")
        self.assertIn(response.status_code, [302, 403])

    def test_index_accessible_with_permission(self):
        self.client.force_login(self.user_with_perm)
        response = self.client.get("/sov/")
        self.assertEqual(response.status_code, 200)

    def test_rift_export_plain_text(self):
        self.client.force_login(self.user_with_perm)
        response = self.client.get("/sov/rift-export/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
