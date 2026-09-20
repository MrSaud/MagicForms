"""Process pending outbound delivery rows."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from magicforms.models import FormOutboundDelivery
from magicforms.outbound.http_client import send_outbound_post
from magicforms.outbound.payload import build_outbound_payload

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
RETRY_MINUTES = (1, 5, 30, 120, 360)


def process_delivery(delivery: FormOutboundDelivery) -> None:
    config = delivery.config
    submission = delivery.submission
    submission = (
        type(submission)
        .objects.select_related(
            "form",
            "form__entity",
            "current_step",
            "submitted_by",
            "submitted_by__profile",
            "submitted_by__profile__manager",
        )
        .prefetch_related("values__field")
        .get(pk=submission.pk)
    )
    event = delivery.submission_event
    url = (config.endpoint_url or "").strip()
    delivery.status = FormOutboundDelivery.Status.RUNNING
    delivery.attempt_count += 1
    delivery.request_url = url
    delivery.save(
        update_fields=[
            "status",
            "attempt_count",
            "request_url",
        ]
    )

    try:
        payload = build_outbound_payload(
            config,
            submission,
            trigger=delivery.trigger,
            event=event,
            workflow_decision=delivery.workflow_decision,
            workflow_decision_comment=delivery.workflow_decision_comment,
            request=None,
        )
    except ValueError as exc:
        delivery.status = FormOutboundDelivery.Status.DEAD
        delivery.error_message = str(exc)[:1000]
        delivery.completed_at = timezone.now()
        delivery.save(update_fields=["status", "error_message", "completed_at"])
        return

    body_str = json.dumps(payload, ensure_ascii=False)
    delivery.request_body_redacted = body_str[:8000]
    try:
        status, resp_body, req_headers_redacted, _sent = send_outbound_post(
            config,
            url=url,
            payload=payload,
            idempotency_key=delivery.idempotency_key,
            trigger=delivery.trigger,
            submission_ref=submission.reference_token,
            form_id=submission.form_id,
        )
        delivery.request_headers_redacted = json.dumps(req_headers_redacted)[:4000]
        delivery.response_status = status
        delivery.response_body_truncated = resp_body
        if 200 <= status < 300:
            delivery.status = FormOutboundDelivery.Status.SUCCESS
            delivery.error_message = ""
            delivery.completed_at = timezone.now()
        else:
            raise RuntimeError(f"HTTP {status}: {resp_body[:500]}")
    except Exception as exc:
        delivery.error_message = str(exc)[:1000]
        if delivery.attempt_count >= MAX_ATTEMPTS:
            delivery.status = FormOutboundDelivery.Status.DEAD
            delivery.completed_at = timezone.now()
        else:
            delivery.status = FormOutboundDelivery.Status.PENDING
            delay = RETRY_MINUTES[min(delivery.attempt_count - 1, len(RETRY_MINUTES) - 1)]
            delivery.next_retry_at = timezone.now() + timedelta(minutes=delay)
        logger.warning(
            "Outbound delivery %s failed (attempt %s): %s",
            delivery.pk,
            delivery.attempt_count,
            exc,
        )
    delivery.save()


def process_pending_deliveries(*, limit: int = 50) -> int:
    now = timezone.now()
    qs = (
        FormOutboundDelivery.objects.filter(
            status=FormOutboundDelivery.Status.PENDING,
            next_retry_at__lte=now,
        )
        .select_related("config", "submission", "submission_event")
        .order_by("created_at")[:limit]
    )
    count = 0
    for delivery in qs:
        with transaction.atomic():
            locked = (
                FormOutboundDelivery.objects.select_for_update()
                .filter(
                    pk=delivery.pk,
                    status=FormOutboundDelivery.Status.PENDING,
                )
                .first()
            )
            if not locked:
                continue
            process_delivery(locked)
        count += 1
    return count
