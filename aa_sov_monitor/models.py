from django.db import models
from allianceauth.eveonline.models import EveCharacter, EveAllianceInfo

class SovConfiguration(models.Model):
    discord_webhook_url = models.URLField(blank=True)
    class Meta:
        default_permissions = ()
    def __str__(self):
        return 'SOV Monitor Konfiguration'
    @classmethod
    def get_webhook_url(cls):
        config = cls.objects.first()
        return config.discord_webhook_url if config and config.discord_webhook_url else None

class SovOwner(models.Model):
    alliance = models.OneToOneField(EveAllianceInfo, on_delete=models.CASCADE, related_name='sov_owner')
    character = models.ForeignKey(EveCharacter, on_delete=models.SET_NULL, null=True)
    last_updated = models.DateTimeField(null=True, blank=True)
    class Meta:
        default_permissions = ()
        permissions = (
            ('view_sov', 'Can view SOV Monitor'),
            ('manage_sov', 'Can manage SOV Monitor alliances'),
            ('view_manager', 'Can view SOV Monitor Manager tab'),
        )
    def __str__(self):
        return self.alliance.alliance_name

class SovSystem(models.Model):
    owner = models.ForeignKey(SovOwner, on_delete=models.CASCADE, related_name='systems')
    solar_system_id = models.IntegerField(unique=True)
    solar_system_name = models.CharField(max_length=100, blank=True)
    constellation_name = models.CharField(max_length=100, blank=True)
    region_name = models.CharField(max_length=100, blank=True)
    adm = models.FloatField(default=0)
    has_ihub = models.BooleanField(default=False)
    has_tcu = models.BooleanField(default=False)
    vulnerable_start = models.DateTimeField(null=True, blank=True)
    vulnerable_end = models.DateTimeField(null=True, blank=True)
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
