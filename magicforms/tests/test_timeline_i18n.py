"""Timeline display translation (no database)."""

from django.test import SimpleTestCase
from django.utils import translation

from magicforms.timeline_i18n import timeline_event_message_display


class TimelineMessageI18nTests(SimpleTestCase):
    def test_form_submitted_ar(self):
        with translation.override("ar"):
            out = timeline_event_message_display("Form submitted.")
        self.assertNotEqual(out, "Form submitted.")

    def test_approved_advanced_uses_step_label(self):
        with translation.override("en"):
            out = timeline_event_message_display(
                'Approved; advanced to "Old label in DB".',
                step_label="Current step label",
            )
        self.assertIn("Current step label", out)
        self.assertNotIn("Old label in DB", out)

    def test_comment_and_delegate_suffix(self):
        with translation.override("en"):
            raw = (
                'Approved; advanced to "Step A". [delegate for: alice]\n\n'
                "Comment: Please review"
            )
            out = timeline_event_message_display(raw, step_label="Step A")
        self.assertIn("Comment:", out)
        self.assertIn("Please review", out)
        self.assertIn("delegate", out.lower())
