from django.contrib import admin
from .models import SovConfiguration, SovOwner, SovSystem, SovCampaign, SovUpgrade, SovHubResource, SovHubReagent, AdmHistory


@admin.register(SovConfiguration)
class SovConfigurationAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Discord Webhooks', {
            'fields': ('discord_webhook_url', 'webhook_adm', 'webhook_reagent', 'webhook_module'),
        }),
    )

    def has_add_permission(self, request):
        return not SovConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SovOwner)
class SovOwnerAdmin(admin.ModelAdmin):
    list_display = ['alliance', 'character', 'last_updated']
    actions = ['update_now']

    @admin.action(description='Jetzt von ESI aktualisieren')
    def update_now(self, request, queryset):
        from .tasks import update_sov_data, update_sov_upgrades
        update_sov_data.delay()
        update_sov_upgrades.delay()
        self.message_user(request, 'SOV Update angestoßen.')


@admin.register(SovSystem)
class SovSystemAdmin(admin.ModelAdmin):
    list_display = ['solar_system_name', 'constellation_name', 'region_name', 'adm', 'has_ihub', 'has_tcu']
    list_filter = ['region_name', 'has_ihub', 'has_tcu']
    search_fields = ['solar_system_name', 'constellation_name', 'region_name']


@admin.register(SovCampaign)
class SovCampaignAdmin(admin.ModelAdmin):
    list_display = ['solar_system_name', 'event_type', 'start_time', 'notified']
    list_filter = ['event_type', 'notified']


@admin.register(SovUpgrade)
class SovUpgradeAdmin(admin.ModelAdmin):
    list_display = ['system', 'type_name', 'level', 'power_state']
    list_filter = ['power_state', 'level']
    search_fields = ['type_name', 'system__solar_system_name']


@admin.register(SovHubResource)
class SovHubResourceAdmin(admin.ModelAdmin):
    list_display = ['system', 'power_available', 'power_allocated', 'workforce_available', 'workforce_allocated']


@admin.register(SovHubReagent)
class SovHubReagentAdmin(admin.ModelAdmin):
    list_display = ['system', 'type_name', 'amount', 'burning_per_hour']
    search_fields = ['type_name', 'system__solar_system_name']


@admin.register(AdmHistory)
class AdmHistoryAdmin(admin.ModelAdmin):
    list_display = ['system', 'adm', 'industrial_level', 'military_level', 'strategic_level', 'recorded_at']
    list_filter = ['recorded_at']
    search_fields = ['system__solar_system_name']
