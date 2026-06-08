from django.contrib import admin
from .models import SovConfiguration, SovOwner, SovSystem, SovCampaign

@admin.register(SovConfiguration)
class SovConfigurationAdmin(admin.ModelAdmin):
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
        from .tasks import update_sov_data
        update_sov_data.delay()
        self.message_user(request, 'SOV Update angestoßen.')

@admin.register(SovSystem)
class SovSystemAdmin(admin.ModelAdmin):
    list_display = ['solar_system_name', 'region_name', 'adm', 'has_ihub', 'has_tcu']
    list_filter = ['region_name', 'has_ihub']

@admin.register(SovCampaign)
class SovCampaignAdmin(admin.ModelAdmin):
    list_display = ['solar_system_name', 'event_type', 'start_time', 'notified']
