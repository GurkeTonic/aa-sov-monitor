# AA SOV Monitor<a name="aa-sov-monitor"></a>

[![Release](https://img.shields.io/github/v/release/GurkeTonic/aa-sov-monitor?label=release)](https://github.com/GurkeTonic/aa-sov-monitor/releases)
[![License](https://img.shields.io/badge/license-GPL--3.0-green)](https://github.com/GurkeTonic/aa-sov-monitor/blob/main/LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/aa-sov-monitor)](https://pypi.org/project/aa-sov-monitor/)
[![Django](https://img.shields.io/pypi/frameworkversions/django/aa-sov-monitor?label=django)](https://pypi.org/project/aa-sov-monitor/)
[![Alliance Auth Compatibility](https://img.shields.io/badge/Alliance_Auth-v5-brightgreen)](https://gitlab.com/allianceauth/allianceauth)

An [Alliance Auth](https://gitlab.com/allianceauth/allianceauth) plugin for EVE Online sovereignty monitoring.
Track ADM levels, IHUB upgrade states, active SOV campaigns, reagent fuel health, and module states — all in one place.

______________________________________________________________________

- [AA SOV Monitor](#aa-sov-monitor)
  - [Features](#features)
  - [Installation](#installation)
    - [Step 1 - Install the Package](#step-1)
    - [Step 2 - Configure Alliance Auth](#step-2)
    - [Step 3 - Run Migrations and Collect Static Files](#step-3)
    - [Step 4 - Restart Services](#step-4)
  - [Configuration](#configuration)
    - [Permissions](#permissions)
    - [Discord Webhooks](#discord-webhooks)
    - [Celery Beat Tasks](#celery-beat-tasks)
  - [Usage](#usage)
    - [Adding an Alliance](#adding-an-alliance)
    - [Tabs](#tabs)
  - [ESI Endpoints Used](#esi-endpoints-used)
  - [Contributing](#contributing)

______________________________________________________________________

## Features<a name="features"></a>

- **ADM Overview** — All sovereignty systems sorted by ADM (lowest first) with color-coded badges (red below 4.5), development indices (industrial, military, strategic), IHUB presence, vulnerability windows, and 7-day ADM history (min/max)
- **ADM Activity Tracking** — ADM values are recorded every 15 minutes and stored for 30 days, giving you a historical view of ADM development per system
- **Upgrades Pivot Table** — At-a-glance view of Threat Detection Arrays, Prospecting Arrays, and Exploration Detectors per system with level indicators (green = Online, orange = Anchored, red = Offline)
- **Campaign Alerts** — Active SOV campaigns listed in real-time with Discord notifications on new attacks
- **RIFT Export** — Copy IHUB upgrade data to clipboard in RIFT-compatible format with one click
- **Manager Tab** — Hub power and workforce usage bars with reagent fuel countdown per system *(restricted permission)*
- **Discord Alerts** — Separate configurable webhooks for ADM warnings, reagent fuel alerts, and module state changes

______________________________________________________________________

## Installation<a name="installation"></a>

> [!NOTE]
> AA SOV Monitor requires Alliance Auth v5.1 or higher.
> Please make sure to update your Alliance Auth before installing this app.

### Step 1 - Install the Package<a name="step-1"></a>

Make sure you're in the virtual environment (venv) of your Alliance Auth installation, then install the package:

```shell
pip install aa-sov-monitor
```

Or directly from GitHub:

```shell
pip install git+https://github.com/GurkeTonic/aa-sov-monitor.git
```

### Step 2 - Configure Alliance Auth<a name="step-2"></a>

Add the app to your `INSTALLED_APPS` in `local.py`:

```python
INSTALLED_APPS += [
    "aa_sov_monitor",
]
```

### Step 3 - Run Migrations and Collect Static Files<a name="step-3"></a>

```shell
python manage.py migrate
python manage.py collectstatic --noinput
```

### Step 4 - Restart Services<a name="step-4"></a>

```shell
supervisorctl restart myauth:
```

______________________________________________________________________

## Configuration<a name="configuration"></a>

### Permissions<a name="permissions"></a>

Assign permissions to your Auth groups in **Django Admin → Authentication → Groups**:

| Permission | Description |
| :--- | :--- |
| `view_sov` | Access to ADM overview, Upgrades, Campaigns, and RIFT Export tabs |
| `manage_sov` | Add or remove alliances from tracking |
| `view_manager` | Access to the Manager tab (power, workforce, reagents) |

### Discord Webhooks<a name="discord-webhooks"></a>

Four independent webhooks can be configured in **Django Admin → AA SOV Monitor → Sov Configurations**:

| Webhook | Trigger | Behaviour |
| :--- | :--- | :--- |
| **Campaigns** | New SOV attack detected | Immediate alert on new campaign |
| **ADM-Alerts** | System ADM drops below 4.5 | All affected systems bundled in one post; resets automatically when ADM recovers above 4.5 |
| **Reagent-Alerts** | Reagent fuel below 72h (Warning) or 24h (Critical) | Re-alerts on escalation from Warning → Critical |
| **Modul-Alerts** | IHUB upgrade changes power state | Shows old state → new state with Online/Offline indicator |

> [!NOTE]
> All webhooks are optional. Alerts are only sent if a webhook URL is configured.

### Celery Beat Tasks<a name="celery-beat-tasks"></a>

Tasks are registered automatically on startup — no manual configuration needed:

| Task | Schedule | Description |
| :--- | :--- | :--- |
| `update_sov_data` | Every 15 minutes | Fetches sovereignty data and ADM values from ESI |
| `check_campaigns` | Every 2 minutes | Checks for active SOV campaigns |
| `update_sov_upgrades` | Every 30 minutes | Fetches IHUB upgrade states and reagent levels |

______________________________________________________________________

## Usage<a name="usage"></a>

### Adding an Alliance<a name="adding-an-alliance"></a>

1. Click **+ Alliance hinzufügen** in the top navbar (requires `manage_sov` permission)
2. Authorize the ESI token for a character in the alliance's holding corporation

> [!IMPORTANT]
> The character must be a director or have the **Starbase Fuel Technician** role in their corporation for upgrade and reagent data to sync correctly.

3. Wait for the next scheduled sync or trigger a manual update from **Django Admin → Sov Owners → Actions → Jetzt von ESI aktualisieren**

### Tabs<a name="tabs"></a>

**ADM** — Sovereignty map sorted by ADM ascending. Badges are red below 4.5, green at 4.5 and above. Shows development indices (industrial, military, strategic levels), IHUB status, vulnerability windows, and 7-day min/max ADM history per system.

**Upgrades** — Pivot table showing which IHUB upgrades are installed per system and at what level. Filter by constellation, upgrade type, and level. Badge colors indicate power state: green = Online, orange = Anchored, red = Offline.

**Campaigns** — Live list of active sovereignty campaigns targeting your systems.

**RIFT Export** — Generates a text block in RIFT format for all IHUB upgrades. Copy to clipboard and paste directly into the RIFT desktop app.

**Manager** *(restricted)* — Per-hub power and workforce usage shown as progress bars. Reagent bay countdown shows estimated hours until empty per reagent type.

______________________________________________________________________

## ESI Endpoints Used<a name="esi-endpoints-used"></a>

| Endpoint | Auth Required |
| :--- | :---: |
| `GET /sovereignty/systems` | No |
| `GET /sovereignty/campaigns` | No |
| `GET /corporations/{id}/structures/sovereignty-hubs` | Yes |
| `GET /corporations/{id}/structures/sovereignty-hubs/{hub_id}` | Yes |

Required ESI scope: `esi-structures.read_corporation.v1`

> Uses `X-Compatibility-Date` header for ESI versioning per CCP developer guidelines.

______________________________________________________________________

## Contributing<a name="contributing"></a>

Pull requests are welcome. Please open an issue first to discuss what you would like to change.

## License

GPL-3.0-or-later
