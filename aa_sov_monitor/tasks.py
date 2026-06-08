from email.utils import parsedate_to_datetime

import requests
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from allianceauth.services.hooks import get_extension_logger
from esi.models import Token

from .models import SovOwner, SovSystem, SovUpgrade, SovCampaign, SovConfiguration, SovHubResource, SovHubReagent

logger = get_extension_logger(__name__)

ESI_BASE = 'https://esi.evetech.net'
ESI_HEADERS = {'X-Compatibility-Date': '2026-05-19'}
TYPE_TCU = 32226
TYPE_IHUB = 32458


def _get_user_agent():
    email = getattr(settings, 'ESI_USER_CONTACT_EMAIL', 'unknown@example.com')
    return f'aa-sov-monitor/0.1.1 ({email}; +https://github.com/GurkeTonic/aa-sov-monitor)'


def _esi_get(path):
    cache_key = f'esi_sov_pub_{path}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    headers = {**ESI_HEADERS, 'User-Agent': _get_user_agent()}
    resp = requests.get(f'{ESI_BASE}{path}', headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    expires = resp.headers.get('Expires')
    if expires:
        try:
            exp_dt = parsedate_to_datetime(expires)
            ttl = max(60, int(exp_dt.timestamp() - timezone.now().timestamp()))
            cache.set(cache_key, data, timeout=ttl)
        except Exception:
            cache.set(cache_key, data, timeout=300)
    else:
        cache.set(cache_key, data, timeout=300)

    return data


def _esi_get_auth(path, token):
    headers = {
        **ESI_HEADERS,
        'Authorization': f'Bearer {token.valid_access_token()}',
        'User-Agent': _get_user_agent(),
    }
    resp = requests.get(f'{ESI_BASE}{path}', headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _resolve_names(ids):
    if not ids:
        return {}
    try:
        headers = {**ESI_HEADERS, 'User-Agent': _get_user_agent()}
        resp = requests.post(f'{ESI_BASE}/universe/names/', json=list(ids), headers=headers, timeout=30)
        resp.raise_for_status()
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
            data = _esi_get(f'/universe/systems/{sys_id}/')
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
            data = _esi_get(f'/universe/constellations/{const_id}/')
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
        'title': f'SOV Angriff: {campaign.solar_system_name}',
        'color': 0xFF0000,
        'fields': [
            {'name': 'System', 'value': campaign.solar_system_name, 'inline': True},
            {'name': 'Typ', 'value': labels.get(campaign.event_type, campaign.event_type), 'inline': True},
            {'name': 'Start', 'value': campaign.start_time.strftime('%d.%m. %H:%M') + ' UTC', 'inline': True},
        ],
        'footer': {'text': 'AA SOV Monitor'},
    }
    try:
        requests.post(webhook_url, json={'content': '@everyone', 'embeds': [embed]}, timeout=10)
    except Exception as e:
        logger.error('Discord webhook failed: %s', e)


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
        sov_map = _esi_get('/sovereignty/map/')
        sov_structures = _esi_get('/sovereignty/structures/')
    except Exception as e:
        logger.error('Failed to fetch sovereignty data: %s', e)
        return
    our_entries = [s for s in sov_map if s.get('alliance_id') in alliance_ids]
    our_system_ids = {s['system_id'] for s in our_entries}
    details_map = _get_system_details(our_system_ids)
    struct_map = {}
    for struct in sov_structures:
        sid = struct.get('solar_system_id')
        if sid not in our_system_ids:
            continue
        if sid not in struct_map:
            struct_map[sid] = {'has_ihub': False, 'has_tcu': False, 'adm': 0, 'vuln_start': None, 'vuln_end': None}
        type_id = struct.get('structure_type_id')
        if type_id == TYPE_IHUB:
            struct_map[sid]['has_ihub'] = True
            struct_map[sid]['adm'] = struct.get('vulnerability_occupancy_level', 0)
            struct_map[sid]['vuln_start'] = parse_datetime(struct['vulnerable_start_time']) if struct.get('vulnerable_start_time') else None
            struct_map[sid]['vuln_end'] = parse_datetime(struct['vulnerable_end_time']) if struct.get('vulnerable_end_time') else None
        elif type_id == TYPE_TCU:
            struct_map[sid]['has_tcu'] = True
    for entry in our_entries:
        sys_id = entry['system_id']
        owner = owner_map[entry['alliance_id']]
        s = struct_map.get(sys_id, {})
        SovSystem.objects.update_or_create(
            solar_system_id=sys_id,
            defaults={
                'owner': owner,
                'solar_system_name': details_map.get(sys_id, (str(sys_id), '', ''))[0],
                'constellation_name': details_map.get(sys_id, ('', '', ''))[1],
                'region_name': details_map.get(sys_id, ('', '', ''))[2],
                'adm': s.get('adm', 0),
                'has_ihub': s.get('has_ihub', False),
                'has_tcu': s.get('has_tcu', False),
                'vulnerable_start': s.get('vuln_start'),
                'vulnerable_end': s.get('vuln_end'),
            }
        )
    SovSystem.objects.filter(owner__in=owners).exclude(solar_system_id__in=our_system_ids).delete()
    for owner in owners:
        owner.last_updated = timezone.now()
        owner.save(update_fields=['last_updated'])


@shared_task
def update_sov_upgrades():
    for pk in SovOwner.objects.values_list('pk', flat=True):
        update_owner_sov_upgrades.delay(pk)


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
        data = _esi_get_auth(f'/corporations/{corp_id}/structures/sovereignty-hubs', token)
        hubs = data.get('sovereignty_hubs', [])
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
        for r in hub_reagent_data.get(sys_id, []):
            SovHubReagent.objects.create(
                system=system,
                type_id=r['type_id'],
                type_name=reagent_name_map.get(r['type_id'], str(r['type_id'])),
                amount=r.get('amount', 0),
                burning_per_hour=r.get('burning_per_hour', 0),
            )
        system.upgrades.all().delete()
        for u in detail.get('upgrades', []):
            type_id = u['type_id']
            raw_name = name_map.get(type_id, str(type_id))
            rift_name = _format_upgrade_for_rift(raw_name)
            parts = rift_name.rsplit(' ', 1)
            lvl = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
            SovUpgrade.objects.create(
                system=system,
                type_id=type_id,
                type_name=rift_name,
                level=lvl,
                power_state=u.get('power_state', 'Unknown'),
            )


@shared_task
def check_campaigns():
    our_system_ids = set(SovSystem.objects.values_list('solar_system_id', flat=True))
    if not our_system_ids:
        return
    try:
        campaigns_data = _esi_get('/sovereignty/campaigns/')
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
