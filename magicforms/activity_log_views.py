"""Staff-only studio views for the activity audit log."""

from __future__ import annotations

from datetime import datetime

from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from .manage_views import staff_studio_required
from .models import ActivityLog
from .pagination import STUDIO_PER_PAGE_CHOICES, paginate


def _parse_date_param(raw: str):
    d = parse_date((raw or "").strip())
    if not d:
        return None
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(d, datetime.min.time()), tz)


@staff_studio_required
def activity_log_list(request):
    qs = ActivityLog.objects.select_related("user").order_by("-created_at")

    q = (request.GET.get("q") or "").strip()
    channel = (request.GET.get("channel") or "").strip()
    method = (request.GET.get("method") or "").strip().upper()
    source = (request.GET.get("source") or "").strip()
    status_raw = (request.GET.get("status") or "").strip()
    staff_filter = (request.GET.get("staff") or "").strip()
    date_from = _parse_date_param(request.GET.get("date_from"))
    date_to = _parse_date_param(request.GET.get("date_to"))

    if q:
        qs = qs.filter(
            Q(summary__icontains=q)
            | Q(path__icontains=q)
            | Q(username__icontains=q)
            | Q(view_name__icontains=q)
            | Q(object_type__icontains=q)
            | Q(object_id__icontains=q)
        )
    if channel in ActivityLog.Channel.values:
        qs = qs.filter(channel=channel)
    if method:
        qs = qs.filter(http_method__iexact=method)
    if source == "http":
        qs = qs.exclude(http_method="MODEL")
    elif source == "model":
        qs = qs.filter(http_method="MODEL")
    if status_raw.isdigit():
        qs = qs.filter(status_code=int(status_raw))
    if staff_filter == "1":
        qs = qs.filter(is_staff_actor=True)
    elif staff_filter == "0":
        qs = qs.filter(is_staff_actor=False)
    if date_from:
        qs = qs.filter(created_at__gte=date_from)
    if date_to:
        end = date_to.replace(hour=23, minute=59, second=59, microsecond=999999)
        qs = qs.filter(created_at__lte=end)

    logs_page, per_page = paginate(request, qs)

    return render(
        request,
        "magicforms/manage/activity_log_list.html",
        {
            "logs": logs_page,
            "search_q": q,
            "filter_channel": channel,
            "filter_method": method,
            "filter_source": source,
            "filter_status": status_raw,
            "filter_staff": staff_filter,
            "filter_date_from": (request.GET.get("date_from") or "").strip(),
            "filter_date_to": (request.GET.get("date_to") or "").strip(),
            "channel_choices": ActivityLog.Channel.choices,
            "per_page": per_page,
            "per_page_choices": STUDIO_PER_PAGE_CHOICES,
        },
    )


@staff_studio_required
def activity_log_detail(request, pk):
    entry = get_object_or_404(ActivityLog.objects.select_related("user"), pk=pk)
    return render(
        request,
        "magicforms/manage/activity_log_detail.html",
        {"entry": entry},
    )
