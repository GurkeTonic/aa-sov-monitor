"""ESI client provider.

A single, reusable ESI client for the whole app. Construction is lazy — the
OpenAPI spec is only fetched on first ``.client`` access. Filtered to the four
operations this plugin uses to keep the loaded spec (and memory) small.
"""

from esi.openapi_clients import ESIClientProvider

from aa_sov_monitor import (
    __app_name_useragent__,
    __esi_compatibility_date__,
    __github_url__,
    __version__,
)

esi = ESIClientProvider(
    compatibility_date=__esi_compatibility_date__,
    ua_appname=__app_name_useragent__,
    ua_version=__version__,
    ua_url=__github_url__,
    operations=[
        "GetSovereigntySystems",
        "GetSovereigntyCampaigns",
        "GetCorporationsStructuresSovereigntyHubsListing",
        "GetCorporationsStructuresSovereigntyHubsDetail",
    ],
)
