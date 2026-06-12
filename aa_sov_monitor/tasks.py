"""Celery tasks: ESI sync and Discord notifications.

ESI access goes through the django-esi OpenAPI client (see ``providers.py``),
which transparently handles caching, ETags, the floating-window rate limit,
the global error limit, the User-Agent and the compatibility date. Type and
system names are resolved from the local EVE SDE (``eve_sde``) to avoid extra
ESI calls.
"""

from datetime import datetime, timedelta
from time import sleep

import requests
from celery import shared_task

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from allianceauth.services.hooks import get_extension_logger
from allianceauth.services.tasks import QueueOnce
from esi.exceptions import ESIBucketLimitException, ESIErrorLimitException, HTTPNotModified
from esi.models import Token

from .app_settings import SOV_MONITOR_TASKS_TIME_LIMIT
from .constants import (
    ADM_THRESHOLD,
    REAGENT_CRITICAL_HOURS,
    REAGENT_WARNING_HOURS,
)
from .models import (
    AdmHistory,
    SovCampaign,
    SovConfiguration,
    SovHubReagent,
    SovHubResource,
    SovOwner,
    SovSystem,
    SovUpgrade,
)
from .providers import esi

logger = get_extension_logger(__name__)

REQUIRED_SCOPES = ["esi-structures.read_corporation.v1"]

# Transient ESI limits — let Celery retry with backoff instead of failing.
ESI_RETRY = {
    "autoretry_for": (ESIErrorLimitException, ESIBucketLimitException),
    "retry_backoff": 30,
    "retry_kwargs": {"max_retries": 3},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_dt(value):
    """Return a datetime from an ESI value that may already be parsed or a string."""
    if value is None or isinstance(value, datetime):
        return value
    return parse_datetime(str(value))


def _resolve_type_names(type_ids):
    """Resolve {type_id: name} from the local EVE SDE; fall back to the id."""
    result = {tid: str(tid) for tid in type_ids}
    if not type_ids:
        return result
    try:
        from eve_sde.models import ItemType

        for item in ItemType.objects.filter(id__in=type_ids):
            result[item.id] = item.name
    except Exception:
        pass
    return result


def _get_system_details(system_ids):
    """Resolve {system_id: (name, constellation, region)} from the local EVE SDE."""
    result = {sid: (str(sid), "", "") for sid in system_ids}
    if not system_ids:
        return result
    try:
        from eve_sde.models import SolarSystem

        for s in (
            SolarSystem.objects.select_related("constellation__region")
            .filter(id__in=system_ids)
        ):
            const = s.constellation
            region = const.region if const else None
            result[s.id] = (
                s.name,
                const.name if const else "",
                region.name if region else "",
            )
    except Exception:
        logger.warning("SDE system lookup failed; falling back to system ids")
    return result


def _send_discord(payload, webhook_url):
    """Post a payload to a Discord webhook with a small retry/backoff."""
    if not webhook_url:
        return
    for attempt in range(3):
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 2))
                logger.warning("Discord rate limited, retry after %ss", retry_after)
                sleep(min(retry_after, 10))
                continue
            resp.raise_for_status()
            return
        except Exception as e:
            logger.error("Discord webhook failed (attempt %d/3): %s", attempt + 1, e)
            sleep(2 * (attempt + 1))
    logger.error("Discord webhook giving up after 3 attempts")


def _send_campaign_alert(campaign):
    webhook_url = SovConfiguration.get_webhook_url()
    if not webhook_url:
        return
    labels = {
        "tcu_defense": "TCU Defense",
        "ihub_defense": "IHUB Defense",
        "station_defense": "Station Defense",
        "station_freeport": "Station Freeport",
    }
    embed = {
        "title": f"SOV Attack: {campaign.solar_system_name}",
        "color": 0xFF0000,
        "fields": [
            {"name": "System", "value": campaign.solar_system_name, "inline": True},
            {"name": "Type", "value": labels.get(campaign.event_type, campaign.event_type), "inline": True},
            {"name": "Start", "value": campaign.start_time.strftime("%Y-%m-%d %H:%M") + " UTC", "inline": True},
        ],
        "footer": {"text": "AA SOV Monitor"},
    }
    _send_discord({"content": "@everyone", "embeds": [embed]}, webhook_url)


def _send_adm_alert(systems, webhook_url):
    fields = [
        {
            "name": s.solar_system_name,
            "value": f"ADM: **{s.adm:.1f}** | Ind: {s.industrial_level} | Mil: {s.military_level} | Str: {s.strategic_level}",
            "inline": False,
        }
        for s in systems
    ]
    embed = {
        "title": f'⚠️ ADM Warning — {len(systems)} System{"s" if len(systems) > 1 else ""} below {ADM_THRESHOLD}',
        "color": 0xFF6600,
        "fields": fields,
        "footer": {"text": "AA SOV Monitor"},
    }
    _send_discord({"embeds": [embed]}, webhook_url)


def _send_reagent_alert(system, level, reagents, webhook_url):
    color = 0xFF0000 if level == "critical" else 0xFF9900
    label = "CRITICAL" if level == "critical" else "Warning"
    fields = [
        {"name": r["name"], "value": f"{r['hours']}h remaining", "inline": True}
        for r in reagents
    ]
    embed = {
        "title": f"⚠️ Reagent {label} — {system.solar_system_name}",
        "color": color,
        "fields": fields,
        "footer": {"text": "AA SOV Monitor"},
    }
    _send_discord({"embeds": [embed]}, webhook_url)


def _send_module_alert(system, changes, webhook_url):
    fields = []
    for c in changes:
        icon = "\U0001f534" if c["new"] != "Online" else "\U0001f7e2"
        fields.append({
            "name": c["name"],
            "value": f"{icon} {c['old']} → {c['new']}",
            "inline": False,
        })
    any_offline = any(c["new"] != "Online" for c in changes)
    embed = {
        "title": f"\U0001f514 Module Status — {system.solar_system_name}",
        "color": 0xFF0000 if any_offline else 0x00CC44,
        "fields": fields,
        "footer": {"text": "AA SOV Monitor"},
    }
    _send_discord({"embeds": [embed]}, webhook_url)


def _format_upgrade_for_rift(name):
    name = name.replace("Sovereignty Hub Upgrade: ", "")
    for roman, num in [(" III", " 3"), (" II", " 2"), (" I", " 1")]:
        if name.endswith(roman):
            return name[: -len(roman)] + num
    return name


# ---------------------------------------------------------------------------
# ESI sync tasks
# ---------------------------------------------------------------------------
@shared_task(base=QueueOnce, once={"graceful": True}, time_limit=SOV_MONITOR_TASKS_TIME_LIMIT, **ESI_RETRY)
def update_sov_data():
    """Sync sovereignty systems (ADM, development indices, vulnerability)."""
    owners = list(SovOwner.objects.select_related("alliance").all())
    if not owners:
        return
    alliance_ids = {o.alliance.alliance_id for o in owners}
    owner_map = {o.alliance.alliance_id: o for o in owners}
    try:
        result = esi.client.Sovereignty.GetSovereigntySystems().result()
    except HTTPNotModified:
        logger.debug("Sovereignty systems unchanged")
        SovConfiguration.mark_synced()  # data current; record the successful check
        return
    except (ESIErrorLimitException, ESIBucketLimitException):
        raise  # let autoretry handle it
    except Exception as e:
        logger.error("Failed to fetch sovereignty systems: %s", e)
        return

    all_systems = list(getattr(result, "solar_systems", None) or [])
    our_entries = []
    for s in all_systems:
        claim = getattr(s, "claim", None)
        # ``claim`` is a pydantic RootModel wrapping a oneOf (alliance/faction);
        # the variant lives under ``.root``. Fall back to ``claim`` itself so
        # plain test doubles keep working.
        root = getattr(claim, "root", claim) if claim is not None else None
        alliance = getattr(root, "alliance", None) if root is not None else None
        if alliance and getattr(alliance, "alliance_id", None) in alliance_ids:
            our_entries.append((s.solar_system_id, alliance))
    our_system_ids = {sid for sid, _ in our_entries}
    details_map = _get_system_details(our_system_ids)
    now = timezone.now()
    adm_history_records = []
    updated_systems = []
    for sys_id, alliance in our_entries:
        owner = owner_map[alliance.alliance_id]
        dev = getattr(alliance, "development", None)
        adm = getattr(dev, "activity_defense_multiplier", 0) if dev else 0
        ind = getattr(dev, "industrial_level", 0) if dev else 0
        mil = getattr(dev, "military_level", 0) if dev else 0
        strat = getattr(dev, "strategic_level", 0) if dev else 0
        hub = getattr(alliance, "sovereignty_hub", None)
        vuln = getattr(hub, "vulnerability_window", None) if hub else None
        name, const, region = details_map.get(sys_id, (str(sys_id), "", ""))
        system, _ = SovSystem.objects.update_or_create(
            solar_system_id=sys_id,
            defaults={
                "owner": owner,
                "solar_system_name": name,
                "constellation_name": const,
                "region_name": region,
                "adm": adm,
                "industrial_level": ind,
                "military_level": mil,
                "strategic_level": strat,
                "has_ihub": bool(hub),
                "vulnerable_start": _to_dt(getattr(vuln, "start", None)) if vuln else None,
                "vulnerable_end": _to_dt(getattr(vuln, "end", None)) if vuln else None,
            },
        )
        updated_systems.append(system)
        adm_history_records.append(AdmHistory(
            system=system,
            adm=adm,
            industrial_level=ind,
            military_level=mil,
            strategic_level=strat,
        ))
    if adm_history_records:
        AdmHistory.objects.bulk_create(adm_history_records)
    AdmHistory.objects.filter(recorded_at__lt=now - timedelta(days=30)).delete()
    SovSystem.objects.filter(owner__in=owners).exclude(solar_system_id__in=our_system_ids).delete()
    for owner in owners:
        owner.last_updated = timezone.now()
        owner.save(update_fields=["last_updated"])
    # Single, app-wide "last sync" marker shown in the UI (scales with many alliances).
    SovConfiguration.mark_synced()

    # ADM alerts: reset flag once a system recovers, then alert on fresh drops.
    SovSystem.objects.filter(
        solar_system_id__in=our_system_ids, adm__gte=ADM_THRESHOLD, adm_alert_sent=True
    ).update(adm_alert_sent=False)
    adm_webhook = SovConfiguration.get_adm_webhook()
    if adm_webhook:
        low = [s for s in updated_systems if s.adm < ADM_THRESHOLD and not s.adm_alert_sent]
        if low:
            _send_adm_alert(low, adm_webhook)
            SovSystem.objects.filter(pk__in=[s.pk for s in low]).update(adm_alert_sent=True)


@shared_task(base=QueueOnce, once={"graceful": True}, time_limit=SOV_MONITOR_TASKS_TIME_LIMIT)
def update_sov_upgrades():
    """Fan out per owner to fetch IHUB upgrade/resource/reagent details."""
    for pk in SovOwner.objects.values_list("pk", flat=True):
        update_owner_sov_upgrades.apply_async(args=[pk], priority=5)


@shared_task(rate_limit="10/m", time_limit=SOV_MONITOR_TASKS_TIME_LIMIT, **ESI_RETRY)
def update_owner_sov_upgrades(owner_pk):
    try:
        owner = SovOwner.objects.select_related("alliance", "character").get(pk=owner_pk)
    except SovOwner.DoesNotExist:
        return
    if not owner.character:
        logger.warning("No character set for %s", owner)
        return
    token = Token.get_token(owner.character.character_id, REQUIRED_SCOPES)
    if not token:
        logger.warning("No token for %s", owner)
        return
    corp_id = owner.character.corporation_id
    try:
        listing = esi.client.Structures.GetCorporationsStructuresSovereigntyHubsListing(
            corporation_id=corp_id, token=token
        ).result()
    except HTTPNotModified:
        logger.debug("Hub listing unchanged for %s", owner)
        return
    except (ESIErrorLimitException, ESIBucketLimitException):
        raise
    except Exception as e:
        logger.error("Failed to fetch hub list for %s: %s", owner, e)
        return

    hubs = list(getattr(listing, "sovereignty_hubs", None) or [])
    if not hubs:
        return

    all_type_ids = set()
    all_reagent_type_ids = set()
    hub_reagent_data = {}
    hub_details = {}
    for hub in hubs:
        try:
            detail = esi.client.Structures.GetCorporationsStructuresSovereigntyHubsDetail(
                corporation_id=corp_id, sovereignty_hub_id=hub.id, token=token
            ).result()
        except HTTPNotModified:
            continue
        except (ESIErrorLimitException, ESIBucketLimitException):
            raise
        except Exception as e:
            logger.error("Failed to fetch hub detail %s: %s", hub.id, e)
            continue
        hub_details[hub.id] = detail
        for u in getattr(detail, "upgrades", None) or []:
            all_type_ids.add(u.type_id)
        reagent_bay = getattr(detail, "reagent_bay", None)
        for r in (getattr(reagent_bay, "reagents", None) or []) if reagent_bay else []:
            all_reagent_type_ids.add(r.type_id)
            hub_reagent_data.setdefault(hub.solar_system_id, []).append(r)

    name_map = _resolve_type_names(all_type_ids)
    reagent_name_map = _resolve_type_names(all_reagent_type_ids)
    system_id_map = {h.solar_system_id: h.id for h in hubs}

    for sys_id, hub_id in system_id_map.items():
        try:
            system = SovSystem.objects.get(solar_system_id=sys_id)
        except SovSystem.DoesNotExist:
            continue
        detail = hub_details.get(hub_id)
        if detail is None:
            continue
        res = getattr(detail, "resources", None)
        pw = getattr(res, "power", None) if res else None
        wf = getattr(res, "workforce", None) if res else None
        SovHubResource.objects.update_or_create(
            system=system,
            defaults={
                "power_available": getattr(pw, "available", 0) if pw else 0,
                "power_allocated": getattr(pw, "allocated", 0) if pw else 0,
                "workforce_available": getattr(wf, "available", 0) if wf else 0,
                "workforce_allocated": getattr(wf, "allocated", 0) if wf else 0,
            },
        )

        system.hub_reagents.all().delete()
        reagent_alerts = []
        for r in hub_reagent_data.get(sys_id, []):
            bph = getattr(r, "burning_per_hour", 0) or 0
            amount = getattr(r, "amount", 0) or 0
            hours = round(amount / bph) if bph > 0 else None
            type_name = reagent_name_map.get(r.type_id, str(r.type_id))
            SovHubReagent.objects.create(
                system=system,
                type_id=r.type_id,
                type_name=type_name,
                amount=amount,
                burning_per_hour=bph,
            )
            if hours is not None and hours < REAGENT_WARNING_HOURS:
                reagent_alerts.append({"name": type_name, "hours": hours})
        new_reagent_level = ""
        if reagent_alerts:
            new_reagent_level = (
                "critical"
                if any(r["hours"] < REAGENT_CRITICAL_HOURS for r in reagent_alerts)
                else "warning"
            )
        if new_reagent_level and new_reagent_level != system.reagent_alert_level:
            reagent_webhook = SovConfiguration.get_reagent_webhook()
            if reagent_webhook:
                _send_reagent_alert(system, new_reagent_level, reagent_alerts, reagent_webhook)
        if new_reagent_level != system.reagent_alert_level:
            system.reagent_alert_level = new_reagent_level
            system.save(update_fields=["reagent_alert_level"])

        old_upgrade_states = {u.type_id: u.power_state for u in system.upgrades.all()}
        system.upgrades.all().delete()
        module_changes = []
        for u in getattr(detail, "upgrades", None) or []:
            type_id = u.type_id
            raw_name = name_map.get(type_id, str(type_id))
            rift_name = _format_upgrade_for_rift(raw_name)
            parts = rift_name.rsplit(" ", 1)
            lvl = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
            new_state = getattr(u, "power_state", "Unknown") or "Unknown"
            SovUpgrade.objects.create(
                system=system,
                type_id=type_id,
                type_name=rift_name,
                level=lvl,
                power_state=new_state,
            )
            if type_id in old_upgrade_states and old_upgrade_states[type_id] != new_state:
                module_changes.append({"name": rift_name, "old": old_upgrade_states[type_id], "new": new_state})
        if module_changes:
            module_webhook = SovConfiguration.get_module_webhook()
            if module_webhook:
                _send_module_alert(system, module_changes, module_webhook)


@shared_task(base=QueueOnce, once={"graceful": True}, time_limit=SOV_MONITOR_TASKS_TIME_LIMIT, **ESI_RETRY)
def check_campaigns():
    """Track active SOV campaigns targeting our systems; alert on new ones."""
    our_system_ids = set(SovSystem.objects.values_list("solar_system_id", flat=True))
    if not our_system_ids:
        return
    try:
        campaigns_data = esi.client.Sovereignty.GetSovereigntyCampaigns().result()
    except HTTPNotModified:
        logger.debug("Sovereignty campaigns unchanged")
        return
    except (ESIErrorLimitException, ESIBucketLimitException):
        raise
    except Exception as e:
        logger.error("Failed to fetch campaigns: %s", e)
        return

    active_ids = set()
    for c in campaigns_data or []:
        if c.solar_system_id not in our_system_ids:
            continue
        active_ids.add(c.campaign_id)
        try:
            sys_name = SovSystem.objects.get(solar_system_id=c.solar_system_id).solar_system_name
        except SovSystem.DoesNotExist:
            sys_name = str(c.solar_system_id)
        campaign, created = SovCampaign.objects.update_or_create(
            campaign_id=c.campaign_id,
            defaults={
                "solar_system_id": c.solar_system_id,
                "solar_system_name": sys_name,
                "event_type": getattr(c, "event_type", "") or "",
                "attacker_score": getattr(c, "attackers_score", 0) or 0,
                "defender_score": getattr(c, "defender_score", 0) or 0,
                "start_time": _to_dt(getattr(c, "start_time", None)),
            },
        )
        if created:
            _send_campaign_alert(campaign)
            campaign.notified = True
            campaign.save(update_fields=["notified"])
    SovCampaign.objects.exclude(campaign_id__in=active_ids).delete()
