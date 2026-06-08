# AA SOV Monitor

An [Alliance Auth](https://gitlab.com/allianceauth/allianceauth) plugin for EVE Online sovereignty monitoring.
Track ADM levels, IHUB upgrade states, active SOV campaigns, and hub resource health — all in one place.

---

## Features

- **Systems Overview** — All sovereignty systems grouped by Region → Constellation with ADM badges (color-coded by level), IHUB presence, and vulnerability windows
- **Upgrades Pivot Table** — At-a-glance view of Threat Detection Arrays, Prospecting Arrays, and Exploration Detectors per system with level indicators (green = Online, orange = Anchored, red = Offline/Low)
- **RIFT Export** — Copy IHUB upgrade data to clipboard in RIFT-compatible format with one click
- **Campaign Alerts** — Active SOV campaigns listed in real-time with Discord @everyone notifications on new attacks
- **Manager Tab** — Hub power and workforce usage bars with reagent fuel countdown per system *(restricted permission)*

---

## Requirements

- Alliance Auth v5.1+
- An EVE Online character with the ESI scope `esi-structures.read_corporation.v1` registered in Auth
- The character must be a director or have the "Starbase Fuel Technician" role in their corporation

---

## Installation

### 1. Install the package

pip install aa-sov-monitor

Or from GitHub:

pip install git+https://github.com/GurkeTonic/aa-sov-monitor.git

### 2. Add to INSTALLED_APPS

In your local.py:

INSTALLED_APPS += [
    'aa_sov_monitor',
]

### 3. Run migrations

python manage.py migrate

### 4. Restart services

supervisorctl restart myauth:

---

## Configuration

### Permissions

Assign permissions to your Auth groups in Django Admin → Authentication → Groups:

| Permission | Description |
|---|---|
| Can view SOV Monitor | Access to Systems, Upgrades, Campaigns, RIFT Export tabs |
| Can manage SOV Monitor alliances | Add/remove alliances from tracking |
| Can view SOV Monitor Manager tab | Access to the Manager tab (power, workforce, reagents) |

### Discord Webhook (optional)

To receive @everyone pings on new SOV campaigns:

1. Go to Django Admin → AA SOV Monitor → Sov Configurations
2. Add a new entry with your Discord webhook URL

### Celery Beat Tasks

Tasks are registered automatically on startup — no manual configuration needed:

| Task | Schedule |
|---|---|
| update_sov_data | Every 10 minutes |
| check_campaigns | Every 2 minutes |
| update_sov_upgrades | Every 30 minutes |

---

## Usage

### Adding an Alliance

1. Click "+ Alliance hinzufügen" in the top navbar (requires manage_sov permission)
2. Authorize the ESI token for a character in the alliance's holding corporation
3. Wait for the next scheduled task or trigger a manual sync from Django Admin

### Tabs

**Systems** — Sovereignty map sorted by Region → Constellation. ADM badges are color-coded: red (1–2), yellow (3), blue (4), green (5+).

**Upgrades** — Pivot table showing which IHUB upgrades are installed per system and at what level. Filter by constellation, upgrade type, and minimum level. Badge colors indicate power state.

**Campaigns** — Live list of active sovereignty campaigns targeting your systems.

**RIFT Export** — Generates a text block in RIFT format for all Online IHUB upgrades. Copy to clipboard and paste directly into the RIFT desktop app.

**Manager** *(restricted)* — Per-hub power and workforce usage shown as progress bars. Reagent bay countdown shows estimated hours until empty per reagent type.

---

## ESI Endpoints Used

| Endpoint | Auth Required |
|---|---|
| /sovereignty/map/ | No |
| /sovereignty/structures/ | No |
| /sovereignty/campaigns/ | No |
| /corporations/{id}/structures/sovereignty-hubs | Yes |
| /corporations/{id}/structures/sovereignty-hubs/{hub_id} | Yes |

Required scope: esi-structures.read_corporation.v1

---

## Contributing

Pull requests are welcome. Please open an issue first to discuss what you would like to change.

## License

MIT
