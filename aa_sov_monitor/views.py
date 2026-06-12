from collections import defaultdict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.db.models import Min, Max
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from allianceauth.eveonline.models import EveCharacter, EveAllianceInfo
from allianceauth.services.hooks import get_extension_logger
from esi.decorators import token_required

from .constants import RIFT_ALLOWED
from .models import SovOwner, SovSystem, SovCampaign, SovConfiguration, AdmHistory

logger = get_extension_logger(__name__)


def _base_name(type_name):
    parts = type_name.rsplit(' ', 1)
    return parts[0] if len(parts) == 2 and parts[1].isdigit() else type_name


@permission_required('aa_sov_monitor.view_sov')
def index(request):
    owner_count = SovOwner.objects.count()
    systems = list(
        SovSystem.objects
        .select_related('owner__alliance', 'hub_resource')
        .prefetch_related('upgrades', 'hub_reagents')
        .order_by('region_name', 'constellation_name', 'solar_system_name')
    )
    campaigns = SovCampaign.objects.order_by('start_time')

    all_upgrades = []
    for s in systems:
        for u in s.upgrades.all():
            u.base_name = _base_name(u.type_name)
            u._sys = s
            all_upgrades.append(u)
    all_upgrades.sort(key=lambda u: u.type_name)

    rift_lines = [
        f'{u._sys.solar_system_name} -> {u.type_name}'
        for u in all_upgrades
        if u.base_name in RIFT_ALLOWED
    ]

    all_base_names = {u.base_name for u in all_upgrades}
    threat_types = [t for t in ['Minor Threat Detection Array', 'Major Threat Detection Array'] if t in all_base_names]
    prospecting = sorted(bn for bn in all_base_names if 'Prospecting Array' in bn)
    exploration = sorted(bn for bn in all_base_names if 'Exploration Detector' in bn)
    ordered_cols = threat_types + prospecting + exploration
    allowed = set(ordered_cols)

    system_upgrade_map = defaultdict(dict)
    for u in all_upgrades:
        if u.base_name in allowed:
            system_upgrade_map[u.system_id][u.base_name] = (u.level, u.power_state)

    upgrade_constellations = sorted({s.constellation_name for s in systems if s.constellation_name})
    upgrade_levels = sorted({u.level for u in all_upgrades if u.base_name in allowed})
    pivot_rows = [
        {
            'system': s,
            'cells': [(col, system_upgrade_map[s.id].get(col, (None, None))) for col in ordered_cols],
        }
        for s in systems
    ]

    manager_rows = []
    if request.user.has_perm('aa_sov_monitor.view_manager'):
        for s in systems:
            try:
                hr = s.hub_resource
                power_pct = int(hr.power_allocated / hr.power_available * 100) if hr.power_available else 0
                wf_pct = int(hr.workforce_allocated / hr.workforce_available * 100) if hr.workforce_available else 0
            except Exception:
                hr = None
                power_pct = wf_pct = 0
            reagents = []
            for r in s.hub_reagents.all():
                hours = round(r.amount / r.burning_per_hour) if r.burning_per_hour > 0 else None
                reagents.append({'type_name': r.type_name, 'amount': r.amount, 'burn': r.burning_per_hour, 'hours': hours})
            manager_rows.append({
                'system': s,
                'power_allocated': hr.power_allocated if hr else 0,
                'power_available': hr.power_available if hr else 0,
                'power_pct': power_pct,
                'wf_allocated': hr.workforce_allocated if hr else 0,
                'wf_available': hr.workforce_available if hr else 0,
                'wf_pct': wf_pct,
                'reagents': reagents,
            })

    week_ago = timezone.now() - timedelta(days=7)
    adm_stats = (
        AdmHistory.objects
        .filter(system__in=systems, recorded_at__gte=week_ago)
        .values('system_id')
        .annotate(adm_min=Min('adm'), adm_max=Max('adm'))
    )
    adm_stats_map = {r['system_id']: r for r in adm_stats}
    adm_rows = sorted(
        [{'system': s, 'stats': adm_stats_map.get(s.id)} for s in systems],
        key=lambda r: r['system'].adm,
    )

    return render(request, 'aa_sov_monitor/index.html', {
        'last_sync': SovConfiguration.get_last_sync(),
        'owner_count': owner_count,
        'systems': systems,
        'campaigns': campaigns,
        'rift_text': '\n'.join(rift_lines),
        'active_campaigns': campaigns.count(),
        'upgrade_count': sum(1 for u in all_upgrades if u.base_name in allowed),
        'ordered_cols': ordered_cols,
        'upgrade_constellations': upgrade_constellations,
        'upgrade_levels': upgrade_levels,
        'pivot_rows': pivot_rows,
        'manager_rows': manager_rows,
        'adm_rows': adm_rows,
    })


@permission_required('aa_sov_monitor.manage_sov')
@token_required(scopes=['esi-structures.read_corporation.v1'])
def add_owner(request, token):
    try:
        character = EveCharacter.objects.get(character_id=token.character_id)
    except EveCharacter.DoesNotExist:
        messages.error(request, _('Character not found in Auth.'))
        return redirect('aa_sov_monitor:index')
    if not character.alliance_id:
        messages.error(request, _('Character is not in an alliance.'))
        return redirect('aa_sov_monitor:index')
    try:
        alliance = EveAllianceInfo.objects.get(alliance_id=character.alliance_id)
    except EveAllianceInfo.DoesNotExist:
        alliance = EveAllianceInfo.objects.create_alliance(character.alliance_id)
    SovOwner.objects.update_or_create(alliance=alliance, defaults={'character': character})
    messages.success(request, _('%(alliance)s added to SOV Monitor.') % {'alliance': alliance.alliance_name})
    return redirect('aa_sov_monitor:index')


@permission_required('aa_sov_monitor.view_sov')
def rift_export(request):
    systems = SovSystem.objects.prefetch_related('upgrades').filter(has_ihub=True)
    lines = []
    for system in systems:
        for upgrade in system.upgrades.all():
            if _base_name(upgrade.type_name) in RIFT_ALLOWED:
                lines.append(f'{system.solar_system_name} -> {upgrade.type_name}')
    return HttpResponse('\n'.join(lines), content_type='text/plain')
