"""Build public form layout: optional collapsible sections + inline/stack field groups."""

from .dynamic_forms import field_collects_answer
from .models import FieldType


def _joins_inline_row(ff) -> bool:
    """True when the field may share a horizontal row with neighbors."""
    return bool(ff.inline) and ff.field_type != FieldType.BREAK


def _groups_for_field_run(form, run):
    """Turn a consecutive list of FormField into ('inline'|'stack', pairs) groups."""
    buf = []
    groups = []
    for ff in run:
        if not field_collects_answer(ff):
            if _joins_inline_row(ff):
                buf.append((ff, None))
            else:
                if buf:
                    groups.append(("inline", buf))
                    buf = []
                groups.append(("stack", [(ff, None)]))
            continue
        bf = form[f"f_{ff.pk}"]
        if _joins_inline_row(ff):
            buf.append((ff, bf))
        else:
            if buf:
                groups.append(("inline", buf))
                buf = []
            groups.append(("stack", [(ff, bf)]))
    if buf:
        groups.append(("inline", buf))
    return groups


def build_public_layout_blocks(form, fields_def, form_model):
    """
    List of dicts: {'section': FormSection|None, 'groups': [(kind, pairs), ...]}.
    Fields are split into runs where section_id is constant (global field order).
    """
    if not fields_def:
        return []

    runs = []
    cur = []
    prev_sid = object()

    for ff in fields_def:
        sid = ff.section_id
        if cur and sid != prev_sid:
            runs.append(cur)
            cur = []
        cur.append(ff)
        prev_sid = sid
    if cur:
        runs.append(cur)

    blocks = []
    used_section_ids = set()
    for run in runs:
        sec = run[0].section if run[0].section_id else None
        if sec:
            used_section_ids.add(sec.pk)
        blocks.append(
            {
                "section": sec,
                "groups": _groups_for_field_run(form, run),
            }
        )

    for s in form_model.get_ordered_sections():
        if s.pk not in used_section_ids:
            blocks.append({"section": s, "groups": []})

    return blocks
