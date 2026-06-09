from django.apps import AppConfig
from aa_sov_monitor import __version__


class AaSovMonitorConfig(AppConfig):
    name = 'aa_sov_monitor'
    label = 'aa_sov_monitor'
    verbose_name = f'SOV Monitor v{__version__}'

    def ready(self):
        from celery import current_app
        from celery.schedules import crontab
        current_app.conf.beat_schedule['aa_sov_monitor_update'] = {
            'task': 'aa_sov_monitor.tasks.update_sov_data',
            'schedule': crontab(minute='*/15'),
            'apply_offset': True,
        }
        current_app.conf.beat_schedule['aa_sov_monitor_upgrades'] = {
            'task': 'aa_sov_monitor.tasks.update_sov_upgrades',
            'schedule': crontab(minute='*/30'),
            'apply_offset': True,
        }
        current_app.conf.beat_schedule['aa_sov_monitor_campaigns'] = {
            'task': 'aa_sov_monitor.tasks.check_campaigns',
            'schedule': crontab(minute='*/2'),
            'apply_offset': True,
        }
