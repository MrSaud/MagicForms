"""Submission timeline sharing."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from magicforms.models import Entity, EntityMembership, Form, FormSubmission, SubmissionTimelineShare
from magicforms.timeline_shares import (
    dismiss_timeline_share_for_user,
    parse_share_user_ids_from_post,
    set_submission_timeline_shares,
    shared_timelines_for_user,
    user_has_timeline_share,
    user_may_view_submission_timeline,
)

User = get_user_model()


class TimelineShareTests(TestCase):
    def setUp(self):
        self.entity = Entity.objects.create(name="Org", slug="org-tl")
        self.staff = User.objects.create_user("staff_tl", password="x", is_staff=True)
        self.member = User.objects.create_user("member_tl", password="x", is_staff=False)
        self.other = User.objects.create_user("other_tl", password="x", is_staff=False)
        for u in (self.staff, self.member, self.other):
            EntityMembership.objects.create(user=u, entity=self.entity)
        self.form = Form.objects.create(
            entity=self.entity,
            title="F",
            slug="f-tl",
            is_published=True,
        )
        self.submission = FormSubmission.objects.create(form=self.form)

    def test_staff_can_share_and_grant_access(self):
        set_submission_timeline_shares(self.staff, self.submission, user_ids=[self.other.pk])
        self.assertTrue(user_has_timeline_share(self.other, self.submission))
        self.assertFalse(user_has_timeline_share(self.member, self.submission))

    def test_shared_user_can_open_timeline_page(self):
        set_submission_timeline_shares(self.staff, self.submission, user_ids=[self.other.pk])
        self.client.force_login(self.other)
        url = reverse(
            "manage:submission_timeline",
            kwargs={"pk": self.form.pk, "submission_id": self.submission.pk},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "mf-timeline")

    def test_shared_user_without_scope_gets_404_on_manage_detail(self):
        set_submission_timeline_shares(self.staff, self.submission, user_ids=[self.other.pk])
        self.client.force_login(self.other)
        url = reverse(
            "manage:submission_manage_detail",
            kwargs={"pk": self.form.pk, "submission_id": self.submission.pk},
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_share_targets_ignore_users_outside_entity(self):
        outsider = User.objects.create_user("outsider_tl", password="x")
        set_submission_timeline_shares(
            self.staff,
            self.submission,
            user_ids=[self.other.pk, outsider.pk],
        )
        self.assertTrue(user_has_timeline_share(self.other, self.submission))
        self.assertFalse(user_has_timeline_share(outsider, self.submission))

    def test_parse_share_user_ids_from_sync_field(self):
        class FakePost(dict):
            def getlist(self, key):
                return self.get(key, [])

        post = FakePost({"share_user_ids_sync": "12,34"})
        self.assertEqual(parse_share_user_ids_from_post(post), [12, 34])

    def test_share_message_stored_and_view_marks_opened(self):
        set_submission_timeline_shares(
            self.staff,
            self.submission,
            user_ids=[self.other.pk],
            share_message="Please review today.",
        )
        share = SubmissionTimelineShare.objects.get(submission=self.submission, user=self.other)
        self.assertEqual(share.share_message, "Please review today.")
        self.assertIsNone(share.first_viewed_at)
        self.client.force_login(self.other)
        url = reverse(
            "manage:submission_timeline",
            kwargs={"pk": self.form.pk, "submission_id": self.submission.pk},
        )
        self.client.get(url)
        share.refresh_from_db()
        self.assertIsNotNone(share.first_viewed_at)

    def test_reshare_after_dismiss_shows_on_home_again(self):
        set_submission_timeline_shares(self.staff, self.submission, user_ids=[self.other.pk])
        dismiss_timeline_share_for_user(self.other, self.submission)
        self.assertFalse(shared_timelines_for_user(self.other))
        set_submission_timeline_shares(self.staff, self.submission, user_ids=[self.other.pk])
        self.assertEqual(len(shared_timelines_for_user(self.other)), 1)

    def test_dismiss_removes_from_home_and_revokes_share_access(self):
        set_submission_timeline_shares(self.staff, self.submission, user_ids=[self.other.pk])
        self.client.force_login(self.other)
        dismiss_url = reverse(
            "manage:submission_timeline_dismiss",
            kwargs={"pk": self.form.pk, "submission_id": self.submission.pk},
        )
        resp = self.client.post(dismiss_url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(user_has_timeline_share(self.other, self.submission))
        self.assertFalse(shared_timelines_for_user(self.other))
        self.assertFalse(user_may_view_submission_timeline(self.other, self.submission, None))
