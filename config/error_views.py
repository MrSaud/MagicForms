"""Custom HTTP error pages (used when DEBUG is False)."""

from django.conf import settings
from django.http import HttpResponse
from django.template import Engine, RequestContext
from django.template.context_processors import i18n as i18n_context
from django.utils import translation
from django.views.decorators.csrf import requires_csrf_token

_SAFE_ENGINE: Engine | None = None
_SAFE_PROCESSORS = [i18n_context]


def _safe_engine() -> Engine:
    """Minimal engine without DB-heavy context processors."""
    global _SAFE_ENGINE
    if _SAFE_ENGINE is None:
        _SAFE_ENGINE = Engine(
            dirs=[settings.BASE_DIR / "templates"],
            app_dirs=False,
            libraries={
                "i18n": "django.templatetags.i18n",
                "static": "django.templatetags.static",
            },
        )
    return _SAFE_ENGINE


def _render_safe(
    template_name: str,
    request=None,
    context: dict | None = None,
    *,
    status: int,
) -> HttpResponse:
    if request is not None:
        lang = translation.get_language_from_request(request, check_path=True)
        if lang:
            translation.activate(lang)
    engine = _safe_engine()
    template = engine.get_template(template_name)
    if request is not None:
        ctx = RequestContext(request, context or {}, processors=_SAFE_PROCESSORS)
        body = template.render(ctx)
    else:
        body = template.render(context or {})
    return HttpResponse(body, status=status, content_type="text/html; charset=utf-8")


def page_not_found(request, exception, template_name="404.html"):
    return _render_safe(
        template_name,
        request,
        {"exception": exception},
        status=404,
    )


@requires_csrf_token
def server_error(request, template_name="500.html"):
    return _render_safe(template_name, request, status=500)


def permission_denied(request, exception, template_name="403.html"):
    return _render_safe(
        template_name,
        request,
        {"exception": exception},
        status=403,
    )


def bad_request(request, exception, template_name="400.html"):
    return _render_safe(
        template_name,
        request,
        {"exception": exception},
        status=400,
    )
