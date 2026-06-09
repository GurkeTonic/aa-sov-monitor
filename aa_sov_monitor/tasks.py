from datetime import timedelta
from email.utils import parsedate_to_datetime

import requests
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from allianceauth.services.hooks import get_extension_logger
from esi.models import Token

from aa_sov_monitor import __version__
from .models import SovOwner, SovSystem, SovUpgrade, SovCampaign, SovConfiguration, SovHubResource, SovHubReagent, AdmHistory

logger = get_extension_logger(__name__)

ESI_BASE = 'https://esi.evetech.net'
ESI_HEADERS = {'X-Compatibility-Date': '2026-05-19'}


def _get_user_agent():
    email = getattr(settings, 'ESI_USER_CONTACT_EMAIL', 'unknown@example.com')
    return f'aa-sov-monitor/{__version__} ({email}; +https://github.com/GurkeTonic/aa-sov-monitor)'


def _handle_esi_response(resp):
    remain = int(resp.headers.get('X-ESI-Error-Limit-Remain', 100))
    if remain < 10:
        logger.warning(
            'ESI error limit critical: %d remaining, resets in %ss',
            remain, resp.headers.get('X-ESI-Error-Limit-Reset', '?'),
        )
    if resp.status_code == 429:
        logger.warning('ESI rate limited (429), retry after %ss', resp.headers.get('Retry-After', '?'))
    resp.raise_for_status()


def _cache_with_expires(cache_key, data, resp_headers):
    expires = resp_headers.get('Expires')
    if expires:
        try:
            exp_dt = parsedate_to_datetime(expires)
            ttl = max(60, int(exp_dt.timestamp() - timezone.now().timestamp()))
            cache.set(cache_key, data, timeout=ttl)
            return
        except Exception:
            pass
    cache.set(cache_key, data, timeout=300)


def _esi_get(path):
    cache_key = f'esi_sov_pub_{path}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    headers = {**ESI_HEADERS, 'User-Agent': _get_user_agent()}
    resp = requests.get(f'{ESI_BASE}{path}', headers=headers, timeout=30)
    _handle_esi_response(resp)
    data = resp.json()
    _cache_with_expires(cache_key, data, resp.headers)
    return data


def _esi_get_auth(path, token):
    cache_key = f'esi_sov_auth_{token.character_id}_{path}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    headers = {
        **ESI_HEADERS,
        'Authorization': f'Bearer {token.valid_access_token()}',
        'User-Agent': _get_user_agent(),
    }
    resp = requests.get(f'{ESI_BASE}{path}', headers=headers, timeout=30)
    _handle_esi_response(resp)
    data = resp.json()
    _cache_with_expires(cache_key, data, resp.headers)
    return data


def _esi_get_auth_pages(path, token):
    results = []
    page = 1
    while True:
        cache_key = f'esi_sov_auth_{token.character_id}_{path}_p{page}'
        cached = cache.get(cache_key)
        if cached is not None:
            data, total_pages = cached
        else:
            headers = {
                **ESI_HEADERS,
                'Authorization': f'Bearer {token.valid_access_token()}',
                'User-Agent': _get_user_agent(),
            }
            resp = requests.get(
                f'{ESI_BASE}{path}', headers=headers, params={'page': page}, timeout=30
            )
            _handle_esi_response(resp)
            data = resp.json()
            total_pages = int(resp.headers.get('X-Pages', 1))
            expires = resp.headers.get('Expires')
            ttl = 300
            if expires:
                try:
                    exp_dt = parsedate_to_datetime(expires)
                    ttl = max(60, int(exp_dt.timestamp() - timezone.now().timestamp()))
                except Exception:
                    pass
            cache.set(cache_key, (data, total_pages), timeout=ttl)
        if isinstance(data, list):
            results.extend(data)
        if page >= total_pages:
            break
        page += 1
    return results


def _resolve_names(ids):
    if not ids:
        return {}
    try:
        headers = {**ESI_HEADERS, 'User-Agent': _get_user_agent()}
        resp = requests.post(f'{ESI_BASE}/universe/names', json=list(ids), headers=headers, timeout=30)
        _handle_esi_response(resp)
        return {item['id']: item['name'] for item in resp.json()}
    except Exception as e:
        logger.warning('Name resolution failed: %s', e)
        return {}


def _get_system_details(system_ids):
    result = {}
    try:
        from eve_sde.models import SolarSystem as SdeSys
        for s in SdeSys.objects.select_related('constellation__region').filter(id__in=system_ids):
            result[s.id] = (s.name, s.constellation.name, s.constellation.region.name)
        if len(result) == len(system_ids):
            return result
    except Exception:
        pass
    remaining = set(system_ids) - set(result.keys())
    name_map = _resolve_names(remaining)
    sys_const_map = {}
    const_ids = set()
    for sys_id in remaining:
        try:
            data = _esi_get(f'/universe/systems/{sys_id}')
            const_id = data.get('constellation_id')
            sys_const_map[sys_id] = const_id
            if const_id:
                const_ids.add(const_id)
        except Exception:
            sys_const_map[sys_id] = None
    const_name_map = _resolve_names(const_ids)
    const_region_map = {}
    region_ids = set()
    for const_id in const_ids:
        try:
            data = _esi_get(f'/universe/constellations/{const_id}')
            region_id = data.get('region_id')
            const_region_map[const_id] = region_id
            if region_id:
                region_ids.add(region_id)
        except Exception:
            const_region_map[const_id] = None
    region_name_map = _resolve_names(region_ids)
    for sys_id in remaining:
        const_id = sys_const_map.get(sys_id)
        region_id = const_region_map.get(const_id) if const_id else None
        result[sys_id] = (
            name_map.get(sys_id, str(sys_id)),
            const_name_map.get(const_id, '') if const_id else '',
            region_name_map.get(region_id, '') if region_id else '',
        )
    return result


def _send_campaign_alert(campaign):
    webhook_url = SovConfiguration.get_webhook_url()
    if not webhook_url:
        return
    labels = {
        'tcu_defense': 'TCU Defense',
        'ihub_defense': 'IHUB Defense',
        'station_defense': 'Station Defense',
        'station_freeport': 'Station Freeport',
    }
    embed = {
        'title': f'SOV Attack: {campaign.solar_system_name}',
        'color': 0xFF0000,
        'fields': [
            {'name': 'System', 'value': campaign.solar_system_name, 'inline': True},
            {'name': 'Type', 'value': labels.get(campaign.event_type, campaign.event_type), 'inline': True},
            {'name': 'Start', 'value': campaign.start_time.strftime('%Y-%m-%d %H:%M') + ' UTC', 'inline': True},
        ],
        'footer': {'text': 'AA SOV Monitor'},
    }
    try:
        requests.post(webhook_url, json={'content': '@everyone', 'embeds': [embed]}, timeout=10)
    except Exception as e:
        logger.error('Discord webhook failed: %s', e)


def _send_adm_alert(systems, webhook_url):
    fields = [
        {
            'name': s.solar_system_name,
            'value': f'ADM: **{s.adm:.1f}** | Ind: {s.industrial_level} | Mil: {s.military_level} | Str: {s.strategic_level}',
            'inline': False,
        }
        for s in systems
    ]
    embed = {
        'title': f'⚠️ ADM Warning — {len(systems)} System{"s" if len(systems) > 1 else ""} below 4.5',
        'color': 0xFF6600,
        'fields': fields,
        'footer': {'text': 'AA SOV Monitor'},
    }
    try:
        requests.post(webhook_url, json={'embeds': [embed]}, timeout=10)
    except Exception as e:
        logger.error('ADM alert webhook failed: %s', e)


def _send_reagent_alert(system, level, reagents, webhook_url):
    color = 0xFF0000 if level == 'critical' else 0xFF9900
    label = 'CRITICAL' if level == 'critical' else 'Warning'
    fields = [
        {'name': r['name'], 'value': f"{r['hours']}h remaining", 'inline': True}
        for r in reagents
    ]
    embed = {
        'title': f'⚠️ Reagent {label} — {system.solar_system_name}',
        'color': color,
        'fields': fields,
        'footer': {'text': 'AA SOV Monitor'},
    }
    try:
        requests.post(webhook_url, json={'embeds': [embed]}, timeout=10)
    except Exception as e:
        logger.error('Reagent alert webhook failed: %s', e)


def _send_module_alert(system, changes, webhook_url):
    fields = []
    for c in changes:
        icon = '\U0001f534' if c['new'] != 'Online' else '\U0001f7e2'
        fields.append({
            'name': c['name'],
            'value': f"{icon} {c['old']} → {c['new']}",
            'inline': False,
        })
    any_offline = any(c['new'] != 'Online' for c in changes)
    embed = {
        'title': f'\U0001f514 Module Status — {system.solar_system_name}',
        'color': 0xFF0000 if any_offline else 0x00CC44,
        'fields': fields,
        'footer': {'text': 'AA SOV Monitor'},
    }
    try:
        requests.post(webhook_url, json={'embeds': [embed]}, timeout=10)
    except Exception as e:
        logger.error('Module alert webhook failed: %s', e)


def _format_upgrade_for_rift(name):
    name = name.replace('Sovereignty Hub Upgrade: ', '')
    for roman, num in [(' III', ' 3'), (' II', ' 2'), (' I', ' 1')]:
        if name.endswith(roman):
            return name[:-len(roman)] + num
    return name


@shared_task
def update_sov_data():
    owners = list(SovOwner.objects.select_related('alliance').all())
    if not owners:
        return
    alliance_ids = {o.alliance.alliance_id for o in owners}
    owner_map = {o.alliance.alliance_id: o for o in owners}
    try:
        resp_data = _esi_get('/sovereignty/systems')
    except Exception as e:
        logger.error('Failed to fetch sovereignty systems: %s', e)
        return
    all_systems = resp_data.get('solar_systems', [])
    our_entries = []
    for s in all_systems:
        alliance_claim = s.get('claim', {}).get('alliance', {})
        if alliance_claim.get('alliance_id') in alliance_ids:
            our_entries.append({'solar_system_id': s['solar_system_id'], **alliance_claim})
    our_system_ids = {e['solar_system_id'] for e in our_entries}
    details_map = _get_system_details(our_system_ids)
    now = timezone.now()
    adm_history_records = []
    updated_systems = []
    for entry in our_entries:
        sys_id = entry['solar_system_id']
        owner = owner_map[entry['alliance_id']]
        dev = entry.get('development') or {}
        adm = dev.get('activity_defense_multiplier', 0)
        hub = entry.get('sovereignty_hub') or {}
        vuln = hub.get('vulnerability_window') or {}
        system, _ = SovSystem.objects.update_or_create(
            solar_system_id=sys_id,
            defaults={
                'owner': owner,
                'solar_system_name': details_map.get(sys_id, (str(sys_id), '', ''))[0],
                'constellation_name': details_map.get(sys_id, ('', '', ''))[1],
                'region_name': details_map.get(sys_id, ('', '', ''))[2],
                'adm': adm,
                'industrial_level': dev.get('industrial_level', 0),
                'military_level': dev.get('military_level', 0),
                'strategic_level': dev.get('strategic_level', 0),
                'has_ihub': bool(hub),
                'has_tcu': False,
                'vulnerable_start': parse_datetime(vuln['start']) if vuln.get('start') else None,
                'vulnerable_end': parse_datetime(vuln['end']) if vuln.get('end') else None,
            }
        )
        updated_systems.append(system)
        adm_history_records.append(AdmHistory(
            system=system,
            adm=adm,
            industrial_level=dev.get('industrial_level', 0),
            military_level=dev.get('military_level', 0),
            strategic_level=dev.get('strategic_level', 0),
        ))
    if adm_history_records:
        AdmHistory.objects.bulk_create(adm_history_records)
    AdmHistory.objects.filter(recorded_at__lt=now - timedelta(days=30)).delete()
    SovSystem.objects.filter(owner__in=owners).exclude(solar_system_id__in=our_system_ids).delete()
    for owner in owners:
        owner.last_updated = timezone.now()
        owner.save(update_fields=['last_updated'])
    # ADM alerts
    SovSystem.objects.filter(solar_system_id__in=our_system_ids, adm__gte=4.5, adm_alert_sent=True).update(adm_alert_sent=False)
    adm_webhook = SovConfiguration.get_adm_webhook()
    if adm_webhook:
        low = [s for s in updated_systems if s.adm < 4.5 and not s.adm_alert_sent]
        if low:
            _send_adm_alert(low, adm_webhook)
            SovSystem.objects.filter(pk__in=[s.pk for s in low]).update(adm_alert_sent=True)


@shared_task
def update_sov_upgrades():
    for pk in SovOwner.objects.values_list('pk', flat=True):
        update_owner_sov_upgrades.apply_async(args=[pk], priority=5)


@shared_task(rate_limit='10/m')
def update_owner_sov_upgrades(owner_pk):
    try:
        owner = SovOwner.objects.select_related('alliance', 'character').get(pk=owner_pk)
    except SovOwner.DoesNotExist:
        return
    token = Token.get_token(owner.character.character_id, ['esi-structures.read_corporation.v1'])
    if not token:
        logger.warning('No token for %s', owner)
        return
    corp_id = owner.character.corporation_id
    try:
        hubs_resp = _esi_get_auth(f'/corporations/{corp_id}/structures/sovereignty-hubs', token)
        hubs = hubs_resp.get('sovereignty_hubs', []) if isinstance(hubs_resp, dict) else hubs_resp
    except Exception as e:
        logger.error('Failed to fetch hub list for %s: %s', owner, e)
        return

    all_type_ids = set()
    all_reagent_type_ids = set()
    hub_reagent_data = {}
    hub_details = {}
    for hub in hubs:
        try:
            detail = _esi_get_auth(f'/corporations/{corp_id}/structures/sovereignty-hubs/{hub["id"]}', token)
            hub_details[hub['id']] = detail
            for u in detail.get('upgrades', []):
                all_type_ids.add(u['type_id'])
            for r in detail.get('reagent_bay', {}).get('reagents', []):
                all_reagent_type_ids.add(r['type_id'])
                hub_reagent_data.setdefault(hub['solar_system_id'], []).append(r)
        except Exception as e:
            logger.error('Failed to fetch hub detail %s: %s', hub['id'], e)

    name_map = _resolve_names(all_type_ids)
    reagent_name_map = _resolve_names(all_reagent_type_ids)
    system_id_map = {h['solar_system_id']: h['id'] for h in hubs}

    for sys_id, hub_id in system_id_map.items():
        try:
            system = SovSystem.objects.get(solar_system_id=sys_id)
        except SovSystem.DoesNotExist:
            continue
        detail = hub_details.get(hub_id, {})
        res = detail.get('resources', {})
        pw = res.get('power', {})
        wf = res.get('workforce', {})
        SovHubResource.objects.update_or_create(
            system=system,
            defaults={
                'power_available': pw.get('available', 0),
                'power_allocated': pw.get('allocated', 0),
                'workforce_available': wf.get('available', 0),
                'workforce_allocated': wf.get('allocated', 0),
            }
        )
        system.hub_reagents.all().delete()
        reagent_alerts = []
        for r in hub_reagent_data.get(sys_id, []):
            bph = r.get('burning_per_hour', 0)
            hours = round(r['amount'] / bph) if bph > 0 else None
            SovHubReagent.objects.create(
                system=system,
                type_id=r['type_id'],
                type_name=reagent_name_map.get(r['type_id'], str(r['type_id'])),
                amount=r.get('amount', 0),
                burning_per_hour=bph,
            )
            if hours is not None and hours < 72:
                reagent_alerts.append({'name': reagent_name_map.get(r['type_id'], str(r['type_id'])), 'hours': hours})
        new_reagent_level = ''
        if reagent_alerts:
            new_reagent_level = 'critical' if any(r['hours'] < 24 for r in reagent_alerts) else 'warning'
        reagent_webhook = SovConfiguration.get_reagent_webhook()
        if reagent_webhook and new_reagent_level and new_reagent_level != system.reagent_alert_level:
            _send_reagent_alert(system, new_reagent_level, reagent_alerts, reagent_webhook)
        if new_reagent_level != system.reagent_alert_level:
            system.reagent_alert_level = new_reagent_level
            system.save(update_fields=['reagent_alert_level'])
        old_upgrade_states = {u.type_id: u.power_state for u in system.upgrades.all()}
        system.upgrades.all().delete()
        module_changes = []
        for u in detail.get('upgrades', []):
            type_id = u['type_id']
            raw_name = name_map.get(type_id, str(type_id))
            rift_name = _format_upgrade_for_rift(raw_name)
            parts = rift_name.rsplit(' ', 1)
            lvl = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
            new_state = u.get('power_state', 'Unknown')
            SovUpgrade.objects.create(
                system=system,
                type_id=type_id,
                type_name=rift_name,
                level=lvl,
                power_state=new_state,
            )
            if type_id in old_upgrade_states and old_upgrade_states[type_id] != new_state:
                module_changes.append({'name': rift_name, 'old': old_upgrade_states[type_id], 'new': new_state})
        if module_changes:
            module_webhook = SovConfiguration.get_module_webhook()
            if module_webhook:
                _send_module_alert(system, module_changes, module_webhook)


@shared_task
def check_campaigns():
    our_system_ids = set(SovSystem.objects.values_list('solar_system_id', flat=True))
    if not our_system_ids:
        return
    try:
        campaigns_data = _esi_get('/sovereignty/campaigns')
    except Exception as e:
        logger.error('Failed to fetch campaigns: %s', e)
        return
    active_ids = set()
    for c in campaigns_data:
        if c['solar_system_id'] not in our_system_ids:
            continue
        active_ids.add(c['campaign_id'])
        try:
            sys_name = SovSystem.objects.get(solar_system_id=c['solar_system_id']).solar_system_name
        except SovSystem.DoesNotExist:
            sys_name = str(c['solar_system_id'])
        campaign, created = SovCampaign.objects.update_or_create(
            campaign_id=c['campaign_id'],
            defaults={
                'solar_system_id': c['solar_system_id'],
                'solar_system_name': sys_name,
                'event_type': c.get('event_type', ''),
                'attacker_score': c.get('attackers_score', 0),
                'defender_score': c.get('defender_score', 0),
                'start_time': parse_datetime(c['start_time']),
            }
        )
        if created:
            _send_campaign_alert(campaign)
            campaign.notified = True
            campaign.save(update_fields=['notified'])
    SovCampaign.objects.exclude(campaign_id__in=active_ids).delete()


