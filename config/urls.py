"""URL configuration for MagicForms."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from django.templatetags.static import static as static_url
from django.views.generic import RedirectView

from config.admin_site import admin_site

urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url=static_url("magicforms/img/favicon-32.png"), permanent=False)),
    path("apple-touch-icon.png", RedirectView.as_view(url=static_url("magicforms/img/apple-touch-icon.png"), permanent=False)),
    path("apple-touch-icon-precomposed.png", RedirectView.as_view(url=static_url("magicforms/img/apple-touch-icon.png"), permanent=False)),
    path("admin/", admin_site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/v1/", include("magicforms.api.urls")),
    path("manage/", include("magicforms.urls_manage")),
    path("", include("magicforms.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # CSS/JS from magicforms/static/ (runserver does not serve these when DEBUG is False).
    urlpatterns += staticfiles_urlpatterns()

handler400 = "config.error_views.bad_request"
handler403 = "config.error_views.permission_denied"
handler404 = "config.error_views.page_not_found"
handler500 = "config.error_views.server_error"
