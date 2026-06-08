import logging
from collections import defaultdict
from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from allianceauth.eveonline.models import EveCharacter, EveAllianceInfo
from esi.decorators import token_required
from .models import SovOwner, SovSystem, SovCampaign, SovUpgrade, SovHubResource, SovHubReagent

logger = logging.getLogger(__name__)

@permission_required('aa_sov_monitor.view_sov')
def index(request):
    owners = SovOwner.objects.select_related('alliance').all()
    systems = (
        SovSystem.objects
        .select_related('owner__alliance')
        .prefetch_related('upgrades')
        .order_by('region_name', 'constellation_name', 'solar_system_name')
    )
    campaigns = SovCampaign.objects.order_by('start_time')
    RIFT_ALLOWED = {'Major Threat Detection Array', 'Minor Threat Detection Array', 'Exploration Detector'}
    rift_lines = []
    for system in systems:
        for upgrade in system.upgrades.all():
            parts = upgrade.type_name.rsplit(' ', 1)
            base = parts[0] if len(parts) == 2 and parts[1].isdigit() else upgrade.type_name
            if base in RIFT_ALLOWED:
                rift_lines.append(f'{system.solar_system_name} -> {upgrade.type_name}')

    all_upgrades = list(SovUpgrade.objects.select_related('system').order_by('type_name'))
    for u in all_upgrades:
        parts = u.type_name.rsplit(' ', 1)
        u.base_name = parts[0] if len(parts) == 2 and parts[1].isdigit() else u.type_name

    all_base_names = set(u.base_name for u in all_upgrades)
    threat_types = [t for t in ['Minor Threat Detection Array', 'Major Threat Detection Array'] if t in all_base_names]
    prospecting = sorted(bn for bn in all_base_names if 'Prospecting Array' in bn)
    exploration = sorted(bn for bn in all_base_names if 'Exploration Detector' in bn)
    ordered_cols = threat_types + prospecting + exploration

    allowed = set(ordered_cols)
    system_upgrade_map = defaultdict(dict)
    for u in all_upgrades:
        if u.base_name in allowed:
            system_upgrade_map[u.system_id][u.base_name] = (u.level, u.power_state)

    pivot_systems = list(SovSystem.objects.select_related('owner__alliance').order_by('region_name', 'constellation_name', 'solar_system_name'))
    upgrade_constellations = sorted(set(s.constellation_name for s in pivot_systems if s.constellation_name))
    upgrade_levels = sorted(set(u.level for u in all_upgrades if u.base_name in allowed))

    pivot_rows = [
        {
            'system': s,
            'cells': [(col, system_upgrade_map[s.id].get(col, (None, None))) for col in ordered_cols],
        }
        for s in pivot_systems
    ]

    manager_rows = []
    if request.user.has_perm('aa_sov_monitor.view_manager'):
        for s in SovSystem.objects.select_related('owner__alliance').prefetch_related('hub_reagents').order_by('region_name', 'constellation_name', 'solar_system_name'):
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
    return render(request, 'aa_sov_monitor/index.html', {
        'owners': owners,
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
    })

@permission_required('aa_sov_monitor.manage_sov')
@token_required(scopes=['esi-structures.read_corporation.v1'])
def add_owner(request, token):
    try:
        character = EveCharacter.objects.get(character_id=token.character_id)
    except EveCharacter.DoesNotExist:
        messages.error(request, 'Charakter nicht in Auth gefunden.')
        return redirect('aa_sov_monitor:index')
    if not character.alliance_id:
        messages.error(request, 'Charakter ist in keiner Alliance.')
        return redirect('aa_sov_monitor:index')
    try:
        alliance = EveAllianceInfo.objects.get(alliance_id=character.alliance_id)
    except EveAllianceInfo.DoesNotExist:
        alliance = EveAllianceInfo.objects.create_alliance(character.alliance_id)
    SovOwner.objects.update_or_create(alliance=alliance, defaults={'character': character})
    messages.success(request, f'{alliance.alliance_name} zum SOV Monitor hinzugefügt.')
    return redirect('aa_sov_monitor:index')

@permission_required('aa_sov_monitor.view_sov')
def rift_export(request):
    systems = SovSystem.objects.prefetch_related('upgrades').filter(has_ihub=True)
    lines = []
    for system in systems:
        for upgrade in system.upgrades.all():
            lines.append(f'{system.solar_system_name} <- {upgrade.type_name}')
    return HttpResponse('\n'.join(lines), content_type='text/plain')
