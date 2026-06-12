"""Tests for ESI sync + Discord notification tasks (ESI and SDE mocked)."""

import sys
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

from allianceauth.eveonline.models import EveAllianceInfo, EveCharacter
from esi.exceptions import HTTPNotModified

from aa_sov_monitor import tasks
from aa_sov_monitor.models import (
    SovCampaign,
    SovConfiguration,
    SovHubReagent,
    SovHubResource,
    SovOwner,
    SovSystem,
    SovUpgrade,
)


def _make_owner(alliance_id=99000001, char_id=90000001, corp_id=2001):
    alliance = EveAllianceInfo.objects.create(
        alliance_id=alliance_id,
        alliance_name="Test Alliance",
        alliance_ticker="TEST",
        executor_corp_id=corp_id,
    )
    character = EveCharacter.objects.create(
        character_id=char_id,
        character_name="Owner Char",
        corporation_id=corp_id,
        corporation_name="Test Corp",
        corporation_ticker="TST",
        alliance_id=alliance_id,
        alliance_name="Test Alliance",
    )
    return SovOwner.objects.create(alliance=alliance, character=character)


def _inject_empty_sde():
    """Inject a fake eve_sde so SDE lookups return nothing (name -> str(id))."""
    empty_qs = mock.MagicMock()
    empty_qs.select_related.return_value.filter.return_value = []
    empty_qs.filter.return_value = []
    fake_models = mock.MagicMock(SolarSystem=empty_qs, ItemType=empty_qs)
    sys.modules["eve_sde"] = mock.MagicMock(models=fake_models)
    sys.modules["eve_sde.models"] = fake_models


class TestUpdateSovData(TestCase):
    def setUp(self):
        self.owner = _make_owner()
        _inject_empty_sde()
        self.addCleanup(lambda: sys.modules.pop("eve_sde", None))
        self.addCleanup(lambda: sys.modules.pop("eve_sde.models", None))

    def _system(self, alliance_id, sys_id=30004759, adm=3.2):
        alliance = SimpleNamespace(
            alliance_id=alliance_id,
            development=SimpleNamespace(
                activity_defense_multiplier=adm,
                industrial_level=5,
                military_level=4,
                strategic_level=3,
            ),
            sovereignty_hub=SimpleNamespace(
                id=1000000000001,
                vulnerability_window=SimpleNamespace(
                    start="2026-06-12T20:00:00Z", end="2026-06-12T22:00:00Z"
                ),
            ),
        )
        return SimpleNamespace(solar_system_id=sys_id, claim=SimpleNamespace(alliance=alliance))

    @mock.patch.object(tasks, "esi")
    def test_creates_system_and_history(self, mock_esi):
        op = mock_esi.client.Sovereignty.GetSovereigntySystems
        op.return_value.result.return_value = SimpleNamespace(
            solar_systems=[self._system(self.owner.alliance.alliance_id)]
        )

        tasks.update_sov_data()

        system = SovSystem.objects.get(solar_system_id=30004759)
        self.assertAlmostEqual(system.adm, 3.2)
        self.assertEqual(system.industrial_level, 5)
        self.assertTrue(system.has_ihub)
        self.assertIsNotNone(system.vulnerable_start)
        self.assertEqual(system.adm_history.count(), 1)
        self.assertIsNotNone(SovConfiguration.get_last_sync())

    @mock.patch.object(tasks, "esi")
    def test_ignores_foreign_alliance(self, mock_esi):
        op = mock_esi.client.Sovereignty.GetSovereigntySystems
        op.return_value.result.return_value = SimpleNamespace(
            solar_systems=[self._system(alliance_id=88880000)]
        )

        tasks.update_sov_data()

        self.assertFalse(SovSystem.objects.exists())

    @mock.patch.object(tasks, "_send_adm_alert")
    @mock.patch.object(tasks, "esi")
    def test_adm_alert_sent_for_low_system(self, mock_esi, mock_alert):
        SovConfiguration.objects.create(webhook_adm="https://discord.test/adm")
        op = mock_esi.client.Sovereignty.GetSovereigntySystems
        op.return_value.result.return_value = SimpleNamespace(
            solar_systems=[self._system(self.owner.alliance.alliance_id, adm=2.0)]
        )

        tasks.update_sov_data()

        mock_alert.assert_called_once()
        self.assertTrue(SovSystem.objects.get(solar_system_id=30004759).adm_alert_sent)

    @mock.patch.object(tasks, "esi")
    def test_claim_wrapped_in_rootmodel(self, mock_esi):
        # ESI returns ``claim`` as a pydantic RootModel: the alliance lives
        # under ``claim.root.alliance``, not ``claim.alliance``.
        inner = self._system(self.owner.alliance.alliance_id)
        wrapped = SimpleNamespace(
            solar_system_id=inner.solar_system_id,
            claim=SimpleNamespace(root=inner.claim),
        )
        op = mock_esi.client.Sovereignty.GetSovereigntySystems
        op.return_value.result.return_value = SimpleNamespace(solar_systems=[wrapped])

        tasks.update_sov_data()

        self.assertTrue(SovSystem.objects.filter(solar_system_id=30004759).exists())

    @mock.patch.object(tasks, "esi")
    def test_not_modified_skips(self, mock_esi):
        op = mock_esi.client.Sovereignty.GetSovereigntySystems
        op.return_value.result.side_effect = HTTPNotModified(status_code=304, headers={})

        tasks.update_sov_data()

        self.assertFalse(SovSystem.objects.exists())
        # 304 means data is current — the sync timestamp must still advance.
        self.assertIsNotNone(SovConfiguration.get_last_sync())


class TestUpdateOwnerSovUpgrades(TestCase):
    def setUp(self):
        self.owner = _make_owner()
        self.system = SovSystem.objects.create(
            owner=self.owner, solar_system_id=30004759, solar_system_name="1DQ1-A", has_ihub=True
        )
        _inject_empty_sde()
        self.addCleanup(lambda: sys.modules.pop("eve_sde", None))
        self.addCleanup(lambda: sys.modules.pop("eve_sde.models", None))

    @mock.patch.object(tasks, "esi")
    @mock.patch.object(tasks.Token, "get_token")
    def test_writes_resources_reagents_upgrades(self, mock_token, mock_esi):
        mock_token.return_value = mock.MagicMock()
        listing = mock_esi.client.Structures.GetCorporationsStructuresSovereigntyHubsListing
        listing.return_value.result.return_value = SimpleNamespace(
            sovereignty_hubs=[SimpleNamespace(id=1000000000001, solar_system_id=30004759)]
        )
        detail = mock_esi.client.Structures.GetCorporationsStructuresSovereigntyHubsDetail
        detail.return_value.result.return_value = SimpleNamespace(
            resources=SimpleNamespace(
                power=SimpleNamespace(available=100, allocated=40),
                workforce=SimpleNamespace(available=200, allocated=150),
            ),
            reagent_bay=SimpleNamespace(
                reagents=[SimpleNamespace(type_id=81143, amount=1000, burning_per_hour=10)]
            ),
            upgrades=[SimpleNamespace(type_id=99999, power_state="Online")],
        )

        tasks.update_owner_sov_upgrades(self.owner.pk)

        res = SovHubResource.objects.get(system=self.system)
        self.assertEqual(res.power_allocated, 40)
        self.assertEqual(res.workforce_available, 200)
        self.assertEqual(SovHubReagent.objects.filter(system=self.system).count(), 1)
        self.assertEqual(SovUpgrade.objects.filter(system=self.system).count(), 1)

    @mock.patch.object(tasks, "_send_reagent_alert")
    @mock.patch.object(tasks, "esi")
    @mock.patch.object(tasks.Token, "get_token")
    def test_reagent_alert_on_low_fuel(self, mock_token, mock_esi, mock_alert):
        SovConfiguration.objects.create(webhook_reagent="https://discord.test/reagent")
        mock_token.return_value = mock.MagicMock()
        listing = mock_esi.client.Structures.GetCorporationsStructuresSovereigntyHubsListing
        listing.return_value.result.return_value = SimpleNamespace(
            sovereignty_hubs=[SimpleNamespace(id=1000000000001, solar_system_id=30004759)]
        )
        detail = mock_esi.client.Structures.GetCorporationsStructuresSovereigntyHubsDetail
        # 100 amount / 10 per hour = 10h remaining -> critical (<24h)
        detail.return_value.result.return_value = SimpleNamespace(
            resources=SimpleNamespace(power=None, workforce=None),
            reagent_bay=SimpleNamespace(
                reagents=[SimpleNamespace(type_id=81143, amount=100, burning_per_hour=10)]
            ),
            upgrades=[],
        )

        tasks.update_owner_sov_upgrades(self.owner.pk)

        mock_alert.assert_called_once()
        self.system.refresh_from_db()
        self.assertEqual(self.system.reagent_alert_level, "critical")


class TestCheckCampaigns(TestCase):
    def setUp(self):
        self.owner = _make_owner()
        SovSystem.objects.create(
            owner=self.owner, solar_system_id=30004759, solar_system_name="1DQ1-A"
        )

    @mock.patch.object(tasks, "_send_campaign_alert")
    @mock.patch.object(tasks, "esi")
    def test_new_campaign_creates_and_alerts(self, mock_esi, mock_alert):
        op = mock_esi.client.Sovereignty.GetSovereigntyCampaigns
        op.return_value.result.return_value = [
            SimpleNamespace(
                campaign_id=555,
                solar_system_id=30004759,
                event_type="ihub_defense",
                attackers_score=0.4,
                defender_score=0.6,
                start_time="2026-06-12T20:00:00Z",
            )
        ]

        tasks.check_campaigns()

        campaign = SovCampaign.objects.get(campaign_id=555)
        self.assertTrue(campaign.notified)
        mock_alert.assert_called_once()

    @mock.patch.object(tasks, "esi")
    def test_stale_campaign_removed(self, mock_esi):
        SovCampaign.objects.create(
            campaign_id=111, solar_system_id=30004759, event_type="ihub_defense",
            start_time="2026-06-01T20:00:00Z",
        )
        op = mock_esi.client.Sovereignty.GetSovereigntyCampaigns
        op.return_value.result.return_value = []

        tasks.check_campaigns()

        self.assertFalse(SovCampaign.objects.filter(campaign_id=111).exists())


class TestDiscordRetry(TestCase):
    @mock.patch("aa_sov_monitor.tasks.sleep", return_value=None)
    @mock.patch("aa_sov_monitor.tasks.requests.post")
    def test_retries_then_succeeds(self, mock_post, _mock_sleep):
        ok = mock.MagicMock(status_code=204)
        mock_post.side_effect = [Exception("network"), ok]

        tasks._send_discord({"content": "test"}, "https://discord.test/webhook")

        self.assertEqual(mock_post.call_count, 2)

    @mock.patch("aa_sov_monitor.tasks.requests.post")
    def test_no_webhook_no_post(self, mock_post):
        tasks._send_discord({"content": "test"}, None)
        mock_post.assert_not_called()
