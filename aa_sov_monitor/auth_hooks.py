from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook
import aa_sov_monitor.urls

class SovMenuItemHook(MenuItemHook):
    def __init__(self):
        super().__init__('SOV Monitor', 'fas fa-globe fa-fw', 'aa_sov_monitor:index', 9999)
    def render(self, request):
        if request.user.has_perm('aa_sov_monitor.view_sov'):
            return MenuItemHook.render(self, request)
        return ''

@hooks.register('menu_item_hook')
def register_menu():
    return SovMenuItemHook()

@hooks.register('url_hook')
def register_urls():
    return UrlHook(aa_sov_monitor.urls, 'aa_sov_monitor', r'^sov/')
