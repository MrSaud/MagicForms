"""Organization-scoped directory login API (JSON: tenant_id, username, password)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
import ssl
import urllib.error
import urllib.request
from datetime import date
from typing import Any

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils.text import get_valid_filename, slugify

from .models import (
    USER_SIGNATURE_MAX_PER_USER,
    EmployeeProfile,
    Entity,
    EntityMembership,
    UserSignature,
    WorkflowDelegation,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 12
MAX_USERNAME_LEN = 150

_MIME_TO_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
}


def _directory_api_success(value: Any) -> bool:
    """True when the directory JSON ``success`` field means authentication succeeded."""
    if value is True:
        return True
    if value == 1:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _directory_str(value: Any) -> str:
    """Normalize directory API scalars to a trimmed string (handles null, numbers)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return ""
    return str(value).strip()


def _api_value_present(value: Any) -> bool:
    """True when the API sent a value that may be written (blank/null must not clear the DB)."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple)):
        return bool(value)
    return True


def _apply_str_field(obj, field: str, raw: Any, *, max_len: int | None = None) -> None:
    if not _api_value_present(raw):
        return
    val = _directory_str(raw)
    if max_len is not None:
        val = val[:max_len]
    setattr(obj, field, val)


def _parse_iso_date(value: Any) -> date | None:
    s = _directory_str(value)
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _parse_emergency_contact(raw: Any) -> tuple[str, str]:
    s = _directory_str(raw)
    if not s:
        return "", ""
    for sep in (" — ", " – ", " - ", "|", ","):
        if sep in s:
            name, phone = s.split(sep, 1)
            return name.strip()[:200], phone.strip()[:40]
    if any(ch.isdigit() for ch in s):
        return "", s[:40]
    return s[:200], ""


def _login_response_person(data: dict[str, Any]) -> dict[str, Any] | None:
    """Directory login user payload: new API ``employee`` or legacy ``user``."""
    emp = data.get("employee")
    if isinstance(emp, dict):
        return emp
    user = data.get("user")
    if isinstance(user, dict):
        return user
    return None


def _login_response_ok(data: dict[str, Any]) -> bool:
    person = _login_response_person(data)
    if not person:
        return False
    success = data.get("success")
    if success is not None and not _directory_api_success(success):
        return False
    auth = data.get("auth")
    if isinstance(auth, dict):
        for key in ("internal", "external_api"):
            block = auth.get(key)
            if isinstance(block, dict) and block.get("attempted") and block.get("success") is False:
                return False
    return True


def _org_unit_name(unit: Any) -> str:
    if not isinstance(unit, dict):
        return ""
    return _directory_str(unit.get("name"))


def _primary_organizational_unit(emp: dict[str, Any]) -> dict[str, Any] | None:
    units = emp.get("organizational_units")
    if isinstance(units, list):
        for unit in units:
            if isinstance(unit, dict) and unit.get("is_primary"):
                return unit
        for unit in units:
            if isinstance(unit, dict):
                return unit
    org_unit = emp.get("organizational_unit")
    if isinstance(org_unit, dict):
        return org_unit
    return None


def _is_api_employee_payload(payload: dict[str, Any]) -> bool:
    if payload.get("samAccountName") or payload.get("userPrincipalName"):
        return False
    return bool(payload.get("username") or payload.get("employee_number") or payload.get("user_id"))


def _user_active_from_employee(emp: dict[str, Any]) -> bool:
    status = _directory_str(emp.get("employment_status")).lower()
    if status in ("active", "employed"):
        return True
    if status in ("inactive", "terminated", "resigned", "left", "suspended", "ended"):
        return False
    return True


def _user_active_from_employee_if_present(emp: dict[str, Any]) -> bool | None:
    if not _api_value_present(emp.get("employment_status")):
        return None
    return _user_active_from_employee(emp)


def _apply_api_user_fields(user, payload: dict[str, Any], *, is_create: bool) -> None:
    """Update ``User`` fields from API payload; skip blank values on existing users."""
    email = _directory_str(payload.get("email"))
    first_name = _directory_str(payload.get("first_name"))
    last_name = _directory_str(payload.get("last_name"))
    username = _directory_str(payload.get("username"))

    if is_create:
        user.email = email[:254]
        user.first_name = first_name[:150]
        user.last_name = last_name[:150]
    else:
        _apply_str_field(user, "email", payload.get("email"), max_len=254)
        _apply_str_field(user, "first_name", payload.get("first_name"), max_len=150)
        _apply_str_field(user, "last_name", payload.get("last_name"), max_len=150)
        if _api_value_present(username):
            if user.username.lower() != username.lower():
                User = get_user_model()
                if not User.objects.filter(username__iexact=username).exclude(pk=user.pk).exists():
                    user.username = username[:MAX_USERNAME_LEN]

    active = _user_active_from_employee_if_present(payload)
    if active is not None:
        user.is_active = active
    elif is_create:
        user.is_active = True


def _map_employment_type(raw: Any) -> str:
    key = _directory_str(raw).lower().replace("-", "_")
    choices = {c.value for c in EmployeeProfile.EmploymentType}
    if key in choices:
        return key
    aliases = {
        "fulltime": EmployeeProfile.EmploymentType.FULL_TIME,
        "parttime": EmployeeProfile.EmploymentType.PART_TIME,
    }
    return aliases.get(key, EmployeeProfile.EmploymentType.FULL_TIME)


def _map_gender(raw: Any) -> str:
    key = _directory_str(raw).lower()
    choices = {c.value for c in EmployeeProfile.Gender if c.value}
    return key if key in choices else ""


def _set_unique_profile_char(profile: EmployeeProfile, field: str, value: str, max_len: int) -> None:
    if not value:
        return
    value = value[:max_len]
    qs = EmployeeProfile.objects.filter(**{field: value}).exclude(user=profile.user)
    if not qs.exists():
        setattr(profile, field, value)


def _directory_email(du: dict[str, Any]) -> str:
    """Prefer ``emailAddress``; if absent, use ``userPrincipalName`` when it looks like an email."""
    email = _directory_str(du.get("emailAddress"))
    if email:
        return email[:254]
    upn = _directory_str(du.get("userPrincipalName"))
    if "@" in upn:
        return upn[:254]
    return ""


def entities_with_active_login_api():
    return (
        Entity.objects.filter(is_active=True, login_api_active=True)
        .exclude(login_api_endpoint="")
        .exclude(login_api_token="")
        .filter(login_api_tenant_id__isnull=False)
        .order_by("name")
    )


def resolve_login_entity(post_data, get_params) -> Entity | None:
    """
    Pick which organization's directory API applies for this sign-in attempt.
    If exactly one is configured, use it. If several, require ``login_entity_slug`` in POST
    (or ``entity`` in GET for pre-filled forms).
    """
    qs = entities_with_active_login_api()
    n = qs.count()
    if n == 0:
        return None
    if n == 1:
        return qs.first()
    slug = (post_data.get("login_entity_slug") or get_params.get("entity") or "").strip()
    if not slug:
        return None
    return qs.filter(slug=slug).first()


def _safe_username(sam: str, upn: str, email: str | None) -> str:
    raw = (sam or "").strip()
    if not raw and upn:
        raw = (upn.split("@", 1)[0] if "@" in upn else upn).strip()
    if not raw and email:
        raw = (email.split("@", 1)[0] if "@" in email else email).strip()
    raw = raw or "user"
    raw = re.sub(r"[^\w.@+-]", "_", raw, flags=re.ASCII)[:MAX_USERNAME_LEN]
    if not raw:
        raw = "user"
    return raw[:MAX_USERNAME_LEN]


def _pick_unique_username(base: str, exclude_pk: int | None = None) -> str:
    User = get_user_model()
    candidate = base[:MAX_USERNAME_LEN]
    qs = User.objects.filter(username=candidate)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    if not qs.exists():
        return candidate
    for i in range(2, 1000):
        suffix = f"_{i}"
        candidate = (base[: MAX_USERNAME_LEN - len(suffix)] + suffix)[:MAX_USERNAME_LEN]
        qs2 = User.objects.filter(username=candidate)
        if exclude_pk is not None:
            qs2 = qs2.exclude(pk=exclude_pk)
        if not qs2.exists():
            return candidate
    return (slugify(base) or "user")[:MAX_USERNAME_LEN]


def _decode_signature_base64(raw: Any) -> bytes | None:
    s = _directory_str(raw)
    if not s:
        return None
    if s.lower().startswith("data:") and "," in s:
        s = s.split(",", 1)[1]
    s = re.sub(r"\s+", "", s)
    try:
        return base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError):
        try:
            return base64.b64decode(s)
        except Exception:
            return None


def _signature_file_extension(mime: str, filename: str) -> str:
    mime_key = mime.lower().split(";", 1)[0].strip()
    if mime_key in _MIME_TO_EXT:
        return _MIME_TO_EXT[mime_key]
    fn = (filename or "").lower()
    for ext in ("png", "jpg", "jpeg", "gif", "webp", "svg"):
        if fn.endswith(f".{ext}"):
            return "jpg" if ext == "jpeg" else ext
    return "png"


def _safe_signature_filename(filename: str, ext: str, api_id: int | None, index: int) -> str:
    stem = get_valid_filename(filename) if filename else ""
    if stem.lower().endswith(f".{ext}"):
        return stem[:200]
    base = stem.rsplit(".", 1)[0] if "." in stem else (stem or "signature")
    base = re.sub(r"[^\w.\-]+", "_", base)[:80] or "signature"
    suffix = api_id if api_id is not None else index
    return f"{base}_{suffix}.{ext}"


def _sync_signatures_from_login_response(user, signatures_raw: Any) -> None:
    """Import ``signatures`` from directory login JSON into ``UserSignature`` rows."""
    if not isinstance(signatures_raw, list) or not signatures_raw:
        return

    for idx, item in enumerate(signatures_raw):
        if not isinstance(item, dict):
            continue
        raw_b64 = item.get("base64")
        if not raw_b64:
            continue
        data = _decode_signature_base64(raw_b64)
        if not data:
            logger.warning("Directory login signature decode failed for user_id=%s index=%s", user.pk, idx)
            continue

        content_hash = hashlib.sha256(data).hexdigest()
        api_id_raw = item.get("id")
        api_id: int | None
        try:
            api_id = int(api_id_raw) if api_id_raw is not None else None
        except (TypeError, ValueError):
            api_id = None

        label_raw = item.get("label")
        label = _directory_str(label_raw)[:120] if _api_value_present(label_raw) else ""
        sort_order: int | None = None
        if _api_value_present(item.get("sort_order")):
            try:
                sort_order = int(item.get("sort_order"))
                if sort_order < 0:
                    sort_order = idx
            except (TypeError, ValueError):
                sort_order = idx

        mime = _directory_str(item.get("mime_type"))
        filename = _directory_str(item.get("filename"))
        ext = _signature_file_extension(mime, filename)
        safe_name = _safe_signature_filename(filename, ext, api_id, idx)

        sig = None
        if api_id is not None:
            sig = UserSignature.objects.filter(user=user, directory_api_id=api_id).first()
        if sig is None and label:
            sig = (
                UserSignature.objects.filter(user=user, label__iexact=label, directory_api_id__isnull=True)
                .order_by("sort_order", "id")
                .first()
            )

        if sig is not None and sig.directory_content_sha256 == content_hash and sig.image:
            meta_fields: list[str] = []
            if label and sig.label != label:
                sig.label = label
                meta_fields.append("label")
            if sort_order is not None and sig.sort_order != sort_order:
                sig.sort_order = sort_order
                meta_fields.append("sort_order")
            if meta_fields:
                sig.save(update_fields=meta_fields)
            continue

        if sig is None:
            if UserSignature.objects.filter(user=user).count() >= USER_SIGNATURE_MAX_PER_USER:
                logger.warning("Directory login signature skipped (limit) for user_id=%s", user.pk)
                continue
            sig = UserSignature(user=user)
        sig.label = label or "Official"
        sig.sort_order = sort_order if sort_order is not None else idx
        if api_id is not None:
            sig.directory_api_id = api_id
        sig.directory_content_sha256 = content_hash
        sig.image.save(safe_name, ContentFile(data), save=False)
        sig.save()


def _delegation_is_active_if_present(item: dict[str, Any]) -> bool | None:
    if _api_value_present(item.get("status")):
        status = _directory_str(item.get("status")).lower()
        if status in ("inactive", "ended", "expired", "revoked", "cancelled", "closed"):
            return False
        if status in ("active", "current"):
            return True
    if item.get("is_current") is not None:
        return _directory_api_success(item.get("is_current"))
    return None


def _extract_delegations_block(
    employee_payload: dict[str, Any] | None, login_response: dict[str, Any] | None
) -> dict[str, Any]:
    for src in (login_response, employee_payload):
        if not isinstance(src, dict):
            continue
        block = src.get("delegations")
        if isinstance(block, dict):
            return block
    return {}


def _resolve_user_from_delegation_person(entity: Entity, person: Any) -> Any | None:
    """Find or create a studio user for a delegator/delegatee (match username, then employee_number)."""
    if not isinstance(person, dict):
        return None
    User = get_user_model()
    username = _directory_str(person.get("username"))
    employee_number = _directory_str(person.get("employee_number"))
    email = _directory_str(person.get("email"))[:254]
    first_name = _directory_str(person.get("first_name"))[:150]
    last_name = _directory_str(person.get("last_name"))[:150]
    if not first_name and not last_name:
        full = _directory_str(person.get("name"))
        if full and " " in full.strip():
            first_name, last_name = full.strip().split(" ", 1)
            first_name = first_name[:150]
            last_name = last_name.strip()[:150]
        elif full:
            first_name = full[:150]

    by_username = User.objects.filter(username__iexact=username).first() if username else None
    by_employee_number = None
    if employee_number:
        prof = (
            EmployeeProfile.objects.filter(employee_number=employee_number)
            .select_related("user")
            .first()
        )
        if prof:
            by_employee_number = prof.user

    user = None
    if by_username and by_employee_number and by_username.pk != by_employee_number.pk:
        logger.warning(
            "Directory login delegation user mismatch username=%s employee_number=%s; using employee_number",
            username,
            employee_number,
        )
        user = by_employee_number
    elif by_employee_number:
        user = by_employee_number
    elif by_username:
        user = by_username

    if user is None and email:
        user = User.objects.filter(email__iexact=email).first()
    ext_uid = person.get("user_id")
    if user is None and ext_uid is not None:
        uname = f"uid_{ext_uid}"[:MAX_USERNAME_LEN]
        user = User.objects.filter(username__iexact=uname).first()

    if user is None:
        if not username and not employee_number and not email:
            return None
        base = _safe_username(username, "", email or None)
        uname = _pick_unique_username(base, None)
        user = User(
            username=uname,
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
        )
        user.set_unusable_password()
        user.save()
    else:
        _apply_str_field(user, "email", person.get("email"), max_len=254)
        _apply_str_field(user, "first_name", person.get("first_name"), max_len=150)
        _apply_str_field(user, "last_name", person.get("last_name"), max_len=150)
        if _api_value_present(username):
            if user.username.lower() != username.lower():
                if not User.objects.filter(username__iexact=username).exclude(pk=user.pk).exists():
                    user.username = username[:MAX_USERNAME_LEN]
        user.save()

    EntityMembership.objects.get_or_create(user=user, entity=entity)
    profile, _ = EmployeeProfile.objects.get_or_create(user=user)
    if _api_value_present(person.get("employee_number")):
        _set_unique_profile_char(profile, "employee_number", employee_number, 64)
    profile.save()

    return user


def _find_workflow_delegation_row(
    entity: Entity,
    delegator,
    delegate,
    api_id: int | None,
) -> WorkflowDelegation | None:
    """Match by delegator+delegate (username/employee_number resolution), then directory API id."""
    row = (
        WorkflowDelegation.objects.filter(entity=entity, delegator=delegator, delegate=delegate)
        .order_by("-is_active", "-created_at")
        .first()
    )
    if row is not None:
        return row
    if api_id is not None:
        return WorkflowDelegation.objects.filter(entity=entity, directory_api_id=api_id).first()
    return None


def _upsert_workflow_delegation_from_api(
    entity: Entity,
    login_user,
    item: dict[str, Any],
    *,
    role: str,
    seen_api_ids: list[int],
    seen_pairs: set[tuple[int, int]],
) -> None:
    api_id: int | None = None
    try:
        raw_id = item.get("id")
        if raw_id is not None:
            api_id = int(raw_id)
            seen_api_ids.append(api_id)
    except (TypeError, ValueError):
        api_id = None

    delegatee = item.get("delegatee")
    if delegatee is None:
        delegatee = item.get("delegate")

    if role == "given":
        delegator = login_user
        delegate = _resolve_user_from_delegation_person(entity, delegatee)
    else:
        delegate = login_user
        delegator = _resolve_user_from_delegation_person(entity, item.get("delegator"))

    if delegator is None or delegate is None or delegator.pk == delegate.pk:
        logger.warning(
            "Directory login delegation skipped (users) entity_id=%s api_id=%s role=%s",
            entity.pk,
            api_id,
            role,
        )
        return

    seen_pairs.add((delegator.pk, delegate.pk))

    row = _find_workflow_delegation_row(entity, delegator, delegate, api_id)
    if row is None:
        row = WorkflowDelegation(entity=entity)

    row.delegator = delegator
    row.delegate = delegate
    if api_id is not None:
        row.directory_api_id = api_id
    if _api_value_present(item.get("start_date")):
        parsed = _parse_iso_date(item.get("start_date"))
        if parsed is not None:
            row.valid_from = parsed
    if _api_value_present(item.get("end_date")):
        parsed = _parse_iso_date(item.get("end_date"))
        if parsed is not None:
            row.valid_until = parsed
    _apply_str_field(row, "notes", item.get("notes"), max_len=500)
    active = _delegation_is_active_if_present(item)
    if active is not None:
        row.is_active = active
    row.save()


def _sync_delegations_from_login_response(
    entity: Entity,
    login_user,
    employee_payload: dict[str, Any] | None,
    login_response: dict[str, Any] | None,
) -> None:
    """Import ``employee.delegations`` (given/received) into ``WorkflowDelegation`` rows."""
    block = _extract_delegations_block(employee_payload, login_response)
    given = block.get("given") if isinstance(block.get("given"), list) else []
    received = block.get("received") if isinstance(block.get("received"), list) else []
    if not given and not received:
        return

    seen_api_ids: list[int] = []
    seen_pairs: set[tuple[int, int]] = set()
    for item in given:
        if isinstance(item, dict):
            _upsert_workflow_delegation_from_api(
                entity,
                login_user,
                item,
                role="given",
                seen_api_ids=seen_api_ids,
                seen_pairs=seen_pairs,
            )
    for item in received:
        if isinstance(item, dict):
            _upsert_workflow_delegation_from_api(
                entity,
                login_user,
                item,
                role="received",
                seen_api_ids=seen_api_ids,
                seen_pairs=seen_pairs,
            )

    if not seen_pairs:
        return

    stale = WorkflowDelegation.objects.filter(
        entity=entity,
        directory_api_id__isnull=False,
    ).filter(Q(delegator=login_user) | Q(delegate=login_user))
    stale_pks = [
        row.pk
        for row in stale.only("pk", "delegator_id", "delegate_id")
        if (row.delegator_id, row.delegate_id) not in seen_pairs
    ]
    if stale_pks:
        WorkflowDelegation.objects.filter(pk__in=stale_pks).update(is_active=False)


@transaction.atomic
def upsert_user_from_directory_payload(
    entity: Entity, payload: dict[str, Any], *, login_response: dict[str, Any] | None = None
):
    """Create or update Django user (+ profile, entity membership) from API login payload."""
    if _is_api_employee_payload(payload):
        user = _upsert_from_api_employee(entity, payload, login_response=login_response)
    else:
        user = _upsert_from_ad_user(entity, payload)
    if user and login_response:
        try:
            _sync_signatures_from_login_response(user, login_response.get("signatures"))
        except Exception:
            logger.exception("Directory login signature sync failed for user_id=%s", user.pk)
        try:
            _sync_delegations_from_login_response(entity, user, payload, login_response)
        except Exception:
            logger.exception("Directory login delegation sync failed for user_id=%s", user.pk)
    return user


def _find_user_for_api_employee(emp: dict[str, Any]):
    """Match login employee by username, employee_number, email, or directory user_id."""
    User = get_user_model()
    username = _directory_str(emp.get("username"))
    email = _directory_str(emp.get("email"))
    employee_number = _directory_str(emp.get("employee_number"))

    by_username = User.objects.filter(username__iexact=username).first() if username else None
    by_employee_number = None
    if employee_number:
        prof = (
            EmployeeProfile.objects.filter(employee_number=employee_number)
            .select_related("user")
            .first()
        )
        if prof:
            by_employee_number = prof.user

    user = None
    if by_username and by_employee_number and by_username.pk != by_employee_number.pk:
        logger.warning(
            "Directory login employee mismatch username=%s employee_number=%s; using employee_number",
            username,
            employee_number,
        )
        user = by_employee_number
    elif by_employee_number:
        user = by_employee_number
    elif by_username:
        user = by_username

    if user is None and email:
        user = User.objects.filter(email__iexact=email).first()
    ext_uid = emp.get("user_id")
    if user is None and ext_uid is not None:
        uname = f"uid_{ext_uid}"[:MAX_USERNAME_LEN]
        user = User.objects.filter(username__iexact=uname).first()
    return user, username, email, employee_number


def _apply_department_from_api(
    profile: EmployeeProfile,
    emp: dict[str, Any],
    login_response: dict[str, Any] | None,
) -> None:
    """Department: employee.department, else working_org_unit, else primary org unit."""
    if _api_value_present(emp.get("department")):
        _apply_str_field(profile, "department", emp.get("department"), max_len=200)
        return
    if isinstance(login_response, dict):
        wou = login_response.get("working_org_unit")
        name = _org_unit_name(wou)
        if name:
            profile.department = name[:200]
            return
    primary = _primary_organizational_unit(emp)
    name = _org_unit_name(primary)
    if name:
        profile.department = name[:200]


def _apply_job_title_from_api(profile: EmployeeProfile, emp: dict[str, Any]) -> None:
    if _api_value_present(emp.get("job_title")):
        _apply_str_field(profile, "job_title", emp.get("job_title"), max_len=200)
        return
    primary = _primary_organizational_unit(emp)
    if isinstance(primary, dict):
        position = primary.get("position")
        if isinstance(position, dict) and _api_value_present(position.get("title")):
            profile.job_title = _directory_str(position.get("title"))[:200]


def _sync_reports_to_manager(
    entity: Entity,
    profile: EmployeeProfile,
    login_response: dict[str, Any] | None,
) -> None:
    if not isinstance(login_response, dict):
        return
    reports = login_response.get("reports_to")
    if not isinstance(reports, dict):
        return
    if reports.get("escalated") is True:
        return
    manager_person = reports.get("employee")
    if not isinstance(manager_person, dict) and _api_value_present(reports.get("username")):
        manager_person = reports
    if not isinstance(manager_person, dict):
        return
    manager_user = _resolve_user_from_delegation_person(entity, manager_person)
    if manager_user is not None and manager_user.pk != profile.user_id:
        profile.manager = manager_user


@transaction.atomic
def _upsert_from_api_employee(
    entity: Entity, emp: dict[str, Any], *, login_response: dict[str, Any] | None = None
):
    """Map tenant login API ``employee`` object into User + EmployeeProfile."""
    User = get_user_model()
    user, api_username, email, employee_number = _find_user_for_api_employee(emp)

    if user is None:
        base = _safe_username(api_username, "", email or None)
        uname = _pick_unique_username(base, None)
        user = User(username=uname)
        user.set_unusable_password()
        _apply_api_user_fields(user, emp, is_create=True)
        user.save()
    else:
        _apply_api_user_fields(user, emp, is_create=False)
        user.save()

    profile, _ = EmployeeProfile.objects.get_or_create(user=user)
    if _api_value_present(emp.get("employee_number")):
        _set_unique_profile_char(profile, "employee_number", _directory_str(emp.get("employee_number")), 64)
    if _api_value_present(emp.get("civil_id")):
        _set_unique_profile_char(profile, "civil_id", _directory_str(emp.get("civil_id")), 80)

    _apply_department_from_api(profile, emp, login_response)
    _apply_job_title_from_api(profile, emp)
    _apply_str_field(profile, "office_location", emp.get("work_location"), max_len=255)
    if _api_value_present(emp.get("section_team")) and not profile.notes.strip():
        team = _directory_str(emp.get("section_team"))
        if team:
            profile.notes = f"Section/team: {team}"
    _apply_str_field(profile, "mobile_phone", emp.get("mobile_number"), max_len=40)
    if _api_value_present(emp.get("email")):
        profile.work_email = email[:254]

    if _api_value_present(emp.get("hire_date")):
        hire = _parse_iso_date(emp.get("hire_date"))
        if hire is not None:
            profile.hire_date = hire
    if _api_value_present(emp.get("date_of_birth")):
        birth = _parse_iso_date(emp.get("date_of_birth"))
        if birth is not None:
            profile.birth_date = birth

    if _api_value_present(emp.get("employee_type")):
        profile.employment_type = _map_employment_type(emp.get("employee_type"))

    if _api_value_present(emp.get("gender")):
        mapped = _map_gender(emp.get("gender"))
        if mapped:
            profile.gender = mapped

    _apply_str_field(profile, "nationality", emp.get("nationality"), max_len=120)

    if _api_value_present(emp.get("emergency_contact")):
        ec_name, ec_phone = _parse_emergency_contact(emp.get("emergency_contact"))
        if ec_name:
            profile.emergency_contact_name = ec_name
        if ec_phone:
            profile.emergency_contact_phone = ec_phone

    _sync_reports_to_manager(entity, profile, login_response)

    profile.save()
    EntityMembership.objects.get_or_create(user=user, entity=entity)
    return user


def _ad_enabled_if_present(du: dict[str, Any]) -> bool | None:
    if "enabled" not in du:
        return None
    raw = du.get("enabled")
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(raw, (int, float)):
        return raw != 0
    return bool(raw)


@transaction.atomic
def _upsert_from_ad_user(entity: Entity, du: dict[str, Any]):
    """Create or update Django user (+ profile, entity membership) from legacy AD-style ``user`` object."""
    User = get_user_model()
    email = _directory_email(du)
    sam = _directory_str(du.get("samAccountName"))
    upn = _directory_str(du.get("userPrincipalName"))
    display = _directory_str(du.get("displayName"))
    given = _directory_str(du.get("givenName"))
    surname = _directory_str(du.get("surname"))
    first_name = given or (display.split(" ", 1)[0] if display else "")
    last_name = surname or (
        display.split(" ", 1)[1].strip() if display and " " in display.strip() else ""
    )
    enabled = _ad_enabled_if_present(du)
    if enabled is None:
        enabled = True

    base_username = _safe_username(sam, upn, email or None)
    user = None
    if base_username:
        user = User.objects.filter(username__iexact=base_username).first()
    if user is None and email:
        user = User.objects.filter(email__iexact=email).first()

    if user is None:
        uname = _pick_unique_username(base_username, None)
        user = User(
            username=uname,
            email=email[:254] if email else "",
            first_name=(first_name or "")[:150],
            last_name=(last_name or "")[:150],
            is_active=enabled,
        )
        user.set_unusable_password()
        user.save()
    else:
        if _api_value_present(du.get("emailAddress")) or (
            _api_value_present(du.get("userPrincipalName")) and "@" in upn
        ):
            em = _directory_email(du)
            if em:
                user.email = em[:254]
        if _api_value_present(du.get("givenName")):
            user.first_name = given[:150]
        elif _api_value_present(du.get("displayName")) and display:
            parts = display.split(" ", 1)
            user.first_name = parts[0][:150]
            if len(parts) > 1 and not _api_value_present(du.get("surname")):
                user.last_name = parts[1].strip()[:150]
        if _api_value_present(du.get("surname")):
            user.last_name = surname[:150]
        active = _ad_enabled_if_present(du)
        if active is not None:
            user.is_active = active
        user.save()

    profile, _ = EmployeeProfile.objects.get_or_create(user=user)
    if _api_value_present(du.get("employeeId")):
        eid_short = _directory_str(du.get("employeeId"))[:64]
        if not EmployeeProfile.objects.filter(employee_number=eid_short).exclude(user=user).exists():
            profile.employee_number = eid_short
    _apply_str_field(profile, "department", du.get("department"), max_len=200)
    _apply_str_field(profile, "job_title", du.get("title"), max_len=200)
    _apply_str_field(profile, "office_location", du.get("office"), max_len=255)
    _apply_str_field(profile, "work_phone", du.get("telephoneNumber"), max_len=40)
    profile.save()

    EntityMembership.objects.get_or_create(user=user, entity=entity)

    return user


def _login_api_secret_headers(entity: Entity) -> dict[str, str]:
    """Build a single header for the configured API secret (Bearer vs raw)."""
    token = (entity.login_api_token or "").strip()
    header_name = (getattr(entity, "login_api_key_name", None) or "").strip() or "Authorization"
    if header_name.lower() == "authorization":
        return {"Authorization": f"Bearer {token}"}
    return {header_name: token}


def try_directory_login_or_none(entity: Entity, username: str, password: str):
    """
    POST JSON ``{"tenant_id","username","password"}`` to ``entity.login_api_endpoint`` with the configured auth header.

    The URL must start with ``http://`` or ``https://``. On HTTP ``200``, the body must be JSON with an
    ``employee`` object (tenant API) or legacy ``user`` (Active Directory). Optional ``success`` must not be
    false when present. The person object is mapped into Django (create or update) and the studio session
    logs in. Legacy example::

        {
          "success": true,
          "user": {
            "samAccountName": "jdoe",
            "userPrincipalName": "jdoe@corp.example",
            "displayName": "Jane Doe",
            "givenName": "Jane",
            "surname": "Doe",
            "emailAddress": "jane.doe@corp.example",
            "employeeId": "E123",
            "department": "Finance",
            "title": "Analyst",
            "office": "HQ-3",
            "telephoneNumber": "+15551212",
            "enabled": true
          }
        }

    ``emailAddress`` may be null; a UPN containing ``@`` is then used as the account email.
    Blank or null API values never overwrite existing database fields (only non-empty responses apply).

    Tenant login responses use top-level ``employee``, ``signatures``, ``working_org_unit``, and
    ``reports_to`` (manager). ``employee.delegations`` sync to :class:`~magicforms.models.WorkflowDelegation`
    (matched by ``username`` and ``employee_number``). Blank API values do not overwrite existing fields.

    If the person object is missing/invalid, or ``success`` is explicitly false, returns ``None``.
    The login view treats that as a failed sign-in when directory login applies (no Django password fallback).
    """
    if (
        not entity.login_api_active
        or not entity.login_api_endpoint
        or not entity.login_api_token
        or entity.login_api_tenant_id is None
    ):
        return None
    tenant_id = int(entity.login_api_tenant_id)
    url = (entity.login_api_endpoint or "").strip()
    low = url.lower()
    if not (low.startswith("https://") or low.startswith("http://")):
        return None
    body = json.dumps(
        {
            "tenant_id": tenant_id,
            "username": username,
            "password": password,
        }
    ).encode("utf-8")
    hdrs = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        **_login_api_secret_headers(entity),
    }
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers=hdrs,
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SEC, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        logger.warning(
            "Directory login HTTP error for entity_id=%s: %s %s",
            entity.pk,
            exc.code,
            exc.reason,
        )
        return None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("Directory login request failed for entity_id=%s: %s", entity.pk, exc)
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Directory login returned non-JSON for entity_id=%s", entity.pk)
        return None

    if not isinstance(data, dict) or not _login_response_ok(data):
        logger.warning(
            "Directory login JSON not successful for entity_id=%s (keys=%s)",
            entity.pk,
            list(data.keys()) if isinstance(data, dict) else type(data).__name__,
        )
        return None
    person = _login_response_person(data)
    if person is None:
        logger.warning("Directory login JSON missing employee/user for entity_id=%s", entity.pk)
        return None

    try:
        return upsert_user_from_directory_payload(entity, person, login_response=data)
    except Exception:
        logger.exception("Directory login user upsert failed for entity_id=%s", entity.pk)
        return None
