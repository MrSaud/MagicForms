"""
Public form drafts: save progress without validation and resume later.

The resume token (UUID) is the credential for guests; signed-in users also get
drafts attached to their account. File uploads are never stored in drafts.
"""

from __future__ import annotations

import uuid

from .dynamic_forms import field_collects_answer
from .models import FieldType, FormSubmissionDraft

DRAFT_SESSION_KEY = "mf_draft_tokens"
DRAFT_SESSION_MAX = 50


def collect_draft_post_data(form_class, post) -> dict:
    """Raw posted values for draft storage: ``{"f_<pk>": [values…]}`` (non-empty only)."""
    data: dict[str, list[str]] = {}
    for key in form_class._magicforms_field_keys:
        vals = [str(v) for v in post.getlist(key) if str(v).strip()]
        if vals:
            data[key] = vals
    return data


def draft_form_initial(form_class, draft: FormSubmissionDraft) -> dict:
    """Convert stored draft data into form ``initial`` values."""
    initial: dict = {}
    by_key = {f"f_{ff.pk}": ff for ff in form_class._magicforms_fields_def}
    for key, vals in (draft.data or {}).items():
        ff = by_key.get(key)
        if ff is None or not vals:
            continue
        if ff.field_type == FieldType.FILE:
            continue
        if ff.field_type == FieldType.CHECKBOX:
            initial[key] = str(vals[0]).strip().lower() in ("on", "true", "yes", "1")
        elif ff.field_type == FieldType.CHECKLIST:
            initial[key] = [str(v) for v in vals]
        else:
            initial[key] = str(vals[0])
    return initial


def draft_missing_required_labels(form_class, data: dict) -> list[str]:
    """Labels of mandatory fields still unanswered in the draft (files always count as pending)."""
    labels: list[str] = []
    for ff in form_class._magicforms_fields_def:
        if not field_collects_answer(ff):
            continue
        # Conditionally visible fields are not strictly required (mirrors build_public_form).
        if not ff.required or ff.visibility_control_field_id:
            continue
        key = f"f_{ff.pk}"
        if ff.field_type == FieldType.FILE:
            labels.append(str(ff.label))
            continue
        vals = data.get(key) or []
        if not any(str(v).strip() for v in vals):
            labels.append(str(ff.label))
    return labels


def find_draft(form_def, raw_token: str) -> FormSubmissionDraft | None:
    raw_token = (raw_token or "").strip()
    if not raw_token:
        return None
    try:
        token = uuid.UUID(raw_token)
    except ValueError:
        return None
    return FormSubmissionDraft.objects.filter(resume_token=token, form=form_def).first()


def draft_accessible(draft: FormSubmissionDraft | None, user) -> bool:
    """Account-owned drafts require the same signed-in user; guest drafts only need the token."""
    if draft is None:
        return False
    if draft.user_id is None:
        return True
    return bool(getattr(user, "is_authenticated", False)) and draft.user_id == user.pk


def remember_session_draft(request, draft: FormSubmissionDraft) -> None:
    tokens = list(request.session.get(DRAFT_SESSION_KEY, []))
    token = str(draft.resume_token)
    if token in tokens:
        return
    tokens.append(token)
    request.session[DRAFT_SESSION_KEY] = tokens[-DRAFT_SESSION_MAX:]
    request.session.modified = True


def forget_session_draft(request, token: str) -> None:
    tokens = list(request.session.get(DRAFT_SESSION_KEY, []))
    if token in tokens:
        tokens.remove(token)
        request.session[DRAFT_SESSION_KEY] = tokens
        request.session.modified = True


def session_draft_tokens(request) -> list[str]:
    return [str(t) for t in request.session.get(DRAFT_SESSION_KEY, [])][:DRAFT_SESSION_MAX]


def draft_resume_url(request, draft: FormSubmissionDraft) -> str:
    """Absolute resume URL (skips the intro page, keeps the share key when set)."""
    base = draft.form.build_public_apply_url(request)
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}draft={draft.resume_token}"
