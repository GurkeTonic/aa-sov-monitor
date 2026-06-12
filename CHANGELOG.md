# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-06-12

### Changed
- ESI now uses the django-esi client (caching, rate/error limits, ETags handled for you)
- Single "last sync" line instead of one per alliance
- Discord alerts retry on rate limit
- Menu order moved to `9999` (AA default)

### Fixed
- No systems were stored (sovereignty data read at the wrong level)
- README: correct SDE command and required in-game role

### Added
- German translation
- Test suite and dev tooling

## [0.1.6] - 2026-06-09

### Fixed
- README: corrected install steps, in-game role and SDE setup

## [0.1.5] - 2026-06-09

### Changed
- Switched to `pyproject.toml` build
- UI translated to English, ISO 8601 dates

### Fixed
- Permissions moved to a dedicated model
- Several metadata and Celery schedule fixes

## [0.1.3] - 2026-05-20

### Added
- ADM history with 7-day min/max (kept 30 days)
- Alerts when ADM drops below 4.5

### Changed
- ADM tab sorted lowest first

## [0.1.2] - 2026-05-10

### Added
- Manager tab: hub power/workforce bars and reagent fuel countdown
- RIFT export
- Discord alerts for reagent fuel and module state changes

## [0.1.1] - 2026-04-28

### Added
- Upgrades pivot table with filters
- Discord alert on upgrade power state change

## [0.1.0] - 2026-04-15

### Added
- Initial release: ADM overview, campaigns tab, Discord attack notifications
- Add alliances via ESI token flow
