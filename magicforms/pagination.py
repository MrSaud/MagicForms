"""Shared list pagination for manage studio views."""

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator

# Allowed page sizes (GET ``per_page``).
STUDIO_PER_PAGE_CHOICES = (10, 25, 50, 100, 200)
STUDIO_PER_PAGE_DEFAULT = 50

# Starter sample forms block on the dashboard (separate GET param from ``page``).
SAMPLE_FORMS_PER_PAGE = 10


def parse_per_page(request) -> int:
    raw = (request.GET.get("per_page") or "").strip()
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return STUDIO_PER_PAGE_DEFAULT
    return n if n in STUDIO_PER_PAGE_CHOICES else STUDIO_PER_PAGE_DEFAULT


def paginate(request, queryset, *, per_page: int | None = None):
    """
    Return ``(page_obj, per_page)`` for the current request (GET ``page``, ``per_page``).
    ``queryset`` may be unordered; callers should ``.order_by()`` before calling.
    """
    per_page = per_page if per_page is not None else parse_per_page(request)
    paginator = Paginator(queryset, per_page)
    raw_page = request.GET.get("page") or 1
    try:
        page_obj = paginator.page(raw_page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    return page_obj, per_page


def paginate_sample_forms(request, queryset):
    """
    Paginate the dashboard sample-forms queryset using GET ``sample_page`` (1-based).

    Does not use ``page`` / ``per_page`` so the main forms list pagination stays independent.
    """
    paginator = Paginator(queryset, SAMPLE_FORMS_PER_PAGE)
    raw_page = request.GET.get("sample_page") or 1
    try:
        return paginator.page(raw_page)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)
