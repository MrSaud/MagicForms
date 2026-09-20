from django.apps import AppConfig


class MagicformsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "magicforms"
    verbose_name = "Magic Forms"

    def ready(self):
        from config.admin_site import admin_site

        from . import signals  # noqa: F401
        from .activity_logging import connect_model_activity_signals

        connect_model_activity_signals()

        admin_site.site_header = "MagicForms"
        admin_site.site_title = "MagicForms"
        admin_site.index_title = "Site administration"
