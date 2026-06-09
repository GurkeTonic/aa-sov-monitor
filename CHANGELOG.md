# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.6] - 2026-06-09

### Fixed
- README: corrected required in-game role from "Starbase Fuel Technician" to **Station Manager**
- README: added EVE SDE installation steps (`django-eveonline-sde`, `import_sde`)
- README: removed incorrect `pip install aa-sov-monitor` (package is not on PyPI)
- README: removed ESI Endpoints section

## [0.1.5] - 2026-06-09

### Changed
- Migrated build system from `setup.cfg` to `pyproject.toml` (hatchling); version is now sourced dynamically from `__init__.py`
- All user-facing strings translated to English (UI, Discord embeds, admin actions, flash messages)
- Date formats updated to ISO 8601 (`Y-m-d H:i`) throughout the UI
- User-Agent string now uses the dynamic package version from `__version__`

### Fixed
- Added missing `apply_offset: True` to the `check_campaigns` Celery Beat schedule
- Admin action `.delay()` calls replaced with `.apply_async(priority=5)`
- `__init__.py` now correctly defines `__version__` and `__title__`
- Added unmanaged `General` model to hold app-level permissions (AA plugin convention); permissions moved from `SovOwner`
- `verbose_name` in `AppConfig` now includes the version string

## [0.1.3] - 2026-05-20

### Added
- ADM history tracking (records every 15 min, kept 30 days) with 7-day min/max display in ADM tab
- `AdmHistory` model and migration
- `industrial_level`, `military_level`, `strategic_level` fields on `SovSystem`
- `adm_alert_sent` flag with automatic reset when ADM recovers above 4.5

### Changed
- ADM tab now sorted by ADM ascending (lowest first)

## [0.1.2] - 2026-05-10

### Added
- Manager tab with hub power/workforce progress bars and reagent fuel countdown
- `SovHubResource` and `SovHubReagent` models
- Discord webhooks for reagent fuel alerts (Warning <72h, Critical <24h) and module state changes
- `webhook_adm`, `webhook_reagent`, `webhook_module` fields on `SovConfiguration`
- RIFT Export tab and `/rift-export` endpoint

### Changed
- `update_owner_sov_upgrades` rate-limited to 10/min

## [0.1.1] - 2026-04-28

### Added
- `SovUpgrade` model with `power_state` field
- Upgrades pivot table with filter controls (constellation, type, level)
- Discord alert on upgrade power state change

## [0.1.0] - 2026-04-15

### Added
- Initial release
- `SovOwner`, `SovSystem`, `SovCampaign`, `SovConfiguration` models
- ADM overview tab
- Campaigns tab with Discord notifications on new SOV attacks
- ESI endpoints: `/sovereignty/systems`, `/sovereignty/campaigns`, `/corporations/{id}/structures/sovereignty-hubs`
- Celery Beat tasks: `update_sov_data` (15 min), `check_campaigns` (2 min), `update_sov_upgrades` (30 min)
- `manage_sov` permission for adding alliances via ESI token flow
