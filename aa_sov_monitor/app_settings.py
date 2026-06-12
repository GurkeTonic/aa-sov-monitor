"""App Settings"""

from django.conf import settings

SOV_MONITOR_TASKS_TIME_LIMIT = getattr(
    settings, "SOV_MONITOR_TASKS_TIME_LIMIT", 1200
)
