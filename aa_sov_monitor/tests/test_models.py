"""Tests for models"""

from django.test import TestCase

from aa_sov_monitor.models import SovCampaign, SovConfiguration, SovSystem


class TestSovConfiguration(TestCase):
    def test_webhook_getters_empty_when_no_config(self):
        self.assertIsNone(SovConfiguration.get_webhook_url())
        self.assertIsNone(SovConfiguration.get_adm_webhook())
        self.assertIsNone(SovConfiguration.get_reagent_webhook())
        self.assertIsNone(SovConfiguration.get_module_webhook())

    def test_webhook_getters_return_configured_values(self):
        SovConfiguration.objects.create(
            discord_webhook_url="https://discord.test/campaign",
            webhook_adm="https://discord.test/adm",
            webhook_reagent="https://discord.test/reagent",
            webhook_module="https://discord.test/module",
        )
        self.assertEqual(SovConfiguration.get_webhook_url(), "https://discord.test/campaign")
        self.assertEqual(SovConfiguration.get_adm_webhook(), "https://discord.test/adm")
        self.assertEqual(SovConfiguration.get_reagent_webhook(), "https://discord.test/reagent")
        self.assertEqual(SovConfiguration.get_module_webhook(), "https://discord.test/module")

    def test_empty_string_webhook_returns_none(self):
        SovConfiguration.objects.create(discord_webhook_url="")
        self.assertIsNone(SovConfiguration.get_adm_webhook())


class TestModelStr(TestCase):
    def test_system_str(self):
        s = SovSystem(solar_system_name="1DQ1-A")
        self.assertEqual(str(s), "1DQ1-A")

    def test_campaign_str(self):
        c = SovCampaign(solar_system_name="1DQ1-A", event_type="ihub_defense")
        self.assertEqual(str(c), "1DQ1-A - ihub_defense")
