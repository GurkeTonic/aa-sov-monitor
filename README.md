# AA SOV Monitor

[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)
[![Alliance Auth](https://img.shields.io/badge/alliance--auth-5.1+-orange)](https://gitlab.com/allianceauth/allianceauth)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-green)](LICENSE)

An [Alliance Auth](https://gitlab.com/allianceauth/allianceauth) plugin to monitor EVE Online sovereignty — ADM levels, IHUB upgrade states, active SOV campaigns, reagent fuel health, and module states.

---

## Features

- **ADM Overview** — All sovereignty systems sorted by ADM ascending with color-coded badges (red below 4.5), development indices (industrial, military, strategic), IHUB presence, vulnerability windows, and 7-day min/max history
- **ADM History Tracking** — ADM values recorded every 15 minutes, stored for 30 days
- **Upgrades Pivot Table** — Threat Detection Arrays, Prospecting Arrays, and Exploration Detectors per system with level and power state indicators
- **Campaign Alerts** — Active SOV campaigns in real-time with Discord notifications on new attacks
- **RIFT Export** — One-click copy of IHUB upgrade data in RIFT-compatible format
- **Manager Tab** *(restricted)* — Hub power and workforce usage bars, reagent fuel countdown per system
- **Discord Alerts** — Separate webhooks for SOV attacks, ADM warnings, reagent fuel alerts, and module state changes
- Celery Beat tasks register automatically on startup — no `local.py` configuration required

---

## Requirements

| Requirement | Version |
|---|---|
| Alliance Auth | >= 5.1.0 |
| Python | >= 3.10 |

### ESI Scope

| Scope | Used for |
|---|---|
| `esi-structures.read_corporation.v1` | IHUB upgrade states, hub resources and reagents |

> The character used to authorize an alliance must have the **Station Manager** role in the holding corporation.

---

## Installation

**Step 1 — Install the package**

    pip install git+https://github.com/GurkeTonic/aa-sov-monitor.git

**Step 2 — Install EVE SDE (if not already present)**

    pip install django-eveonline-sde

**Step 3 — Add to `INSTALLED_APPS` in `local.py`**

    INSTALLED_APPS += [
        'aa_sov_monitor',
        'eve_sde',
    ]

**Step 4 — Run migrations and collect static**

    python manage.py migrate
    python manage.py collectstatic

**Step 5 — Load SDE data**

    python manage.py import_sde

**Step 6 — Restart services**

    sudo supervisorctl restart myauth:

---

## Setup

1. Open **SOV Monitor** in the Alliance Auth navigation menu
2. Click **+ Add Alliance** and authenticate with a character that has the **Starbase Fuel Technician** or director role in the holding corporation
3. The first sync runs automatically within 15 minutes, or trigger it manually via **Django Admin → Sov Owners → Actions → Update from ESI now**

---

## Discord Webhooks (optional)

1. Create a Webhook in your Discord server (Channel Settings → Integrations → Webhooks)
2. Go to **Django Admin → AA SOV Monitor → Sov Configurations → Add**
3. Enter the Webhook URL(s) and save

| Webhook | Trigger | Behaviour |
|---|---|---|
| **Campaigns** | New SOV attack detected | Immediate @everyone alert with system, type, and start time |
| **ADM Alerts** | System ADM drops below 4.5 | All affected systems in one post; resets when ADM recovers |
| **Reagent Alerts** | Reagent fuel below 72 h (Warning) or 24 h (Critical) | Re-alerts on escalation Warning → Critical |
| **Module Alerts** | IHUB upgrade changes power state | Shows old state → new state |

All webhooks are optional and independent — alerts are only sent if a URL is configured.

---

## Permissions

| Permission | Description |
|---|---|
| `view_sov` | Access to ADM, Upgrades, Campaigns, and RIFT Export tabs |
| `manage_sov` | Add or remove alliances from tracking |
| `view_manager` | Access to the Manager tab (power, workforce, reagents) |

Assign permissions via **Django Admin → Auth → Groups**.

---

## Tabs

**ADM** — Sovereignty systems sorted by ADM ascending. Red badge below 4.5, green at 4.5 and above. Shows development indices, IHUB status, vulnerability windows, and 7-day min/max ADM history.

**Upgrades** — Pivot table of IHUB upgrades per system. Filter by constellation, upgrade type, and level. Green = Online, orange = Anchored/Pending, red = Offline.

**Campaigns** — Live list of active SOV campaigns targeting your systems.

**RIFT Export** — IHUB upgrade data in RIFT format. Copy to clipboard and paste into the RIFT desktop app.

**Manager** *(restricted)* — Power and workforce usage as progress bars. Reagent bay countdown in hours per reagent type.

---

## Contributing

Pull requests are welcome. For major changes please open an issue first.

---

## License

[GPL-3.0](LICENSE)
