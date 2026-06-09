from django.db import models
from allianceauth.eveonline.models import EveCharacter, EveAllianceInfo


class General(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ('view_sov', 'Can view SOV Monitor'),
            ('manage_sov', 'Can manage SOV Monitor alliances'),
            ('view_manager', 'Can view SOV Monitor Manager tab'),
        )


class SovConfiguration(models.Model):
    discord_webhook_url = models.URLField(blank=True, verbose_name='Webhook: Campaigns')
    webhook_adm = models.URLField(blank=True, verbose_name='Webhook: ADM Alerts')
    webhook_reagent = models.URLField(blank=True, verbose_name='Webhook: Reagent Alerts')
    webhook_module = models.URLField(blank=True, verbose_name='Webhook: Module Alerts')
    class Meta:
        default_permissions = ()
    def __str__(self):
        return 'SOV Monitor Configuration'
    @classmethod
    def _get(cls, field):
        config = cls.objects.first()
        return getattr(config, field, None) or None if config else None
    @classmethod
    def get_webhook_url(cls):
        return cls._get('discord_webhook_url')
    @classmethod
    def get_adm_webhook(cls):
        return cls._get('webhook_adm')
    @classmethod
    def get_reagent_webhook(cls):
        return cls._get('webhook_reagent')
    @classmethod
    def get_module_webhook(cls):
        return cls._get('webhook_module')

class SovOwner(models.Model):
    alliance = models.OneToOneField(EveAllianceInfo, on_delete=models.CASCADE, related_name='sov_owner')
    character = models.ForeignKey(EveCharacter, on_delete=models.SET_NULL, null=True)
    last_updated = models.DateTimeField(null=True, blank=True)
    class Meta:
        default_permissions = ()
    def __str__(self):
        return self.alliance.alliance_name

class SovSystem(models.Model):
    owner = models.ForeignKey(SovOwner, on_delete=models.CASCADE, related_name='systems')
    solar_system_id = models.IntegerField(unique=True)
    solar_system_name = models.CharField(max_length=100, blank=True)
    constellation_name = models.CharField(max_length=100, blank=True)
    region_name = models.CharField(max_length=100, blank=True)
    adm = models.FloatField(default=0)
    industrial_level = models.IntegerField(default=0)
    military_level = models.IntegerField(default=0)
    strategic_level = models.IntegerField(default=0)
    has_ihub = models.BooleanField(default=False)
    has_tcu = models.BooleanField(default=False)
    vulnerable_start = models.DateTimeField(null=True, blank=True)
    vulnerable_end = models.DateTimeField(null=True, blank=True)
    adm_alert_sent = models.BooleanField(default=False)
    reagent_alert_level = models.CharField(max_length=10, default='')
    class Meta:
        default_permissions = ()
    def __str__(self):
        return self.solar_system_name

class SovUpgrade(models.Model):
    system = models.ForeignKey(SovSystem, on_delete=models.CASCADE, related_name='upgrades')
    type_id = models.IntegerField()
    type_name = models.CharField(max_length=255)
    level = models.IntegerField(default=1)
    power_state = models.CharField(max_length=20, default='Online')
    class Meta:
        default_permissions = ()
        unique_together = ('system', 'type_id')
    def __str__(self):
        return f'{self.type_name} {self.level}'

class SovCampaign(models.Model):
    campaign_id = models.IntegerField(unique=True)
    solar_system_id = models.IntegerField()
    solar_system_name = models.CharField(max_length=100, blank=True)
    event_type = models.CharField(max_length=50)
    attacker_score = models.FloatField(default=0)
    defender_score = models.FloatField(default=0)
    start_time = models.DateTimeField()
    notified = models.BooleanField(default=False)
    class Meta:
        default_permissions = ()
    def __str__(self):
        return f'{self.solar_system_name} - {self.event_type}'

class SovHubResource(models.Model):
    system = models.OneToOneField(SovSystem, on_delete=models.CASCADE, related_name='hub_resource')
    power_available = models.IntegerField(default=0)
    power_allocated = models.IntegerField(default=0)
    workforce_available = models.IntegerField(default=0)
    workforce_allocated = models.IntegerField(default=0)
    class Meta:
        default_permissions = ()

class SovHubReagent(models.Model):
    system = models.ForeignKey(SovSystem, on_delete=models.CASCADE, related_name='hub_reagents')
    type_id = models.IntegerField()
    type_name = models.CharField(max_length=255, blank=True)
    amount = models.IntegerField(default=0)
    burning_per_hour = models.FloatField(default=0)
    class Meta:
        default_permissions = ()
        unique_together = ('system', 'type_id')


class AdmHistory(models.Model):
    system = models.ForeignKey(SovSystem, on_delete=models.CASCADE, related_name='adm_history')
    adm = models.FloatField()
    industrial_level = models.IntegerField(default=0)
    military_level = models.IntegerField(default=0)
    strategic_level = models.IntegerField(default=0)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        indexes = [models.Index(fields=['system', 'recorded_at'])]
