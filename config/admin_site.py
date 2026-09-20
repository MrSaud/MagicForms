"""Django admin is limited to superusers; day-to-day work happens in /manage/."""

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User


class SuperuserOnlyAdminSite(admin.AdminSite):
    site_header = "MagicForms administration"
    site_title = "MagicForms admin"
    index_title = "Site administration"

    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser


admin_site = SuperuserOnlyAdminSite(name="admin")
admin_site.register(User, UserAdmin)
admin_site.register(Group, GroupAdmin)
