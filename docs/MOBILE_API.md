# Mobile API (v1)

JSON API on the **main site host** only (no `{entity}` segment in paths). Configure the app base URL from the environment (e.g. `https://your-domain.example`), not a hardcoded hostname.

## Auth

### `POST /api/v1/auth/login/`

Request (`Content-Type: application/json`):

```json
{
  "username": "mosa-kuwait-jdoe",
  "password": "secret"
}
```

Use **organization username** `entity-slug-username` (e.g. `mosa-kuwait-jdoe`). The server splits this into `entity_slug` + `username` (longest matching directory slug). Optional explicit `entity_slug` is still accepted.

When more than one organization uses directory login, the slug prefix is required (same as studio). Use `GET /api/v1/auth/directory-entities/` to list slugs.

**Mobile apps** (`ios/`, `android/`): divided **organization username** UI (`org-slug` + `username`); token stored securely; see each folder’s README.

Success (`200`):

```json
{
  "ok": true,
  "token": "<bearer-token>",
  "expires_at": "2026-06-18T12:00:00+00:00",
  "token_type": "Bearer",
  "login_via": "password",
  "user": { "id": 1, "username": "jdoe", "email": "", "first_name": "", "last_name": "", "full_name": "", "is_staff": true, "is_superuser": false },
  "entities": [{ "id": 1, "slug": "default", "name": "Default", "logo_url": "https://example.com/media/entity_page_logos/2026/05/logo.png" }]
}
```

Each entity may include `logo_url` when an organization logo is configured in **Edit organization → Identity**. The app top bar uses `banner_logo_url` from home summary when the user belongs to exactly one organization.

Use the token on later requests:

`Authorization: Bearer <token>`

### Language

Send the app UI language on every request:

`Accept-Language: en` or `Accept-Language: ar`

The API activates Django locale so form schema labels, choices, and section titles match the selected language (same catalogs as the web portal). You can also pass `?lang=ar` on GET requests.

### `GET /api/v1/auth/me/`

Requires bearer token. Returns current user and entity memberships.

### `POST /api/v1/auth/logout/` or `DELETE /api/v1/auth/logout/`

Revokes the bearer token.

### `GET /api/v1/auth/directory-entities/`

Lists organizations that use directory login (no auth).

## Home (bearer token required)

### `GET /api/v1/home/summary/`

Counts and studio menu URLs for the hamburger menu:

```json
{
  "ok": true,
  "inbox_count": 3,
  "applicant_pending_count": 0,
  "is_staff": true,
  "is_superuser": false,
  "banner_logo_url": "https://example.com/media/entity_page_logos/2026/05/logo.png",
  "banner_entity_name": "Acme Corp",
  "menu_links": {
    "studio_home": "https://…/manage/",
    "inbox": "https://…/manage/inbox/",
    "submission_search": "https://…/manage/submissions/search/",
    "my_signatures": "https://…/account/signatures/",
    "public_site": "https://…/",
    "help": "https://…/manage/help/"
  }
}
```

`inbox_count` matches the studio nav inbox badge (open workflow requests).

`applicant_pending_count` is the number of supplementary (related) forms the user must still complete for submissions they started. Use `GET /api/v1/related/pending/` for the list.

`banner_logo_url` and `banner_entity_name` are set when the user has a single organization membership and that organization has a logo; otherwise they are empty strings (apps show the default SForms branding).

### `GET /api/v1/forms/published/`

Published forms visible to the signed-in user (same rules as the public home / entity portal lists).

### `GET /api/v1/forms/<form_id>/schema/`

Native form fill screen: field definitions, sections, conditional visibility rules, and pre-filled values from user/profile mappings.

Response includes `status` (`open`, `closed`, `already_submitted`, `no_fields`, `unpublished`) and `status_message` when not submittable.

### `POST /api/v1/forms/<form_id>/submit/`

Submit a published form (`multipart/form-data`, same field keys as the public web form: `f_<field_id>`).

- Text-like fields: plain form parts
- Checkbox: `on` when checked
- Checklist: repeated parts with the same key
- File: file part per upload field

Success (`200`):

```json
{
  "ok": true,
  "submission": {
    "id": 42,
    "reference_token": "…",
    "detail_url": "https://…/e/…/f/…/s/…/"
  }
}
```

Validation failure (`400`): `field_errors` map of `f_<id>` → message list.

### Related (supplementary) forms

When a submission triggers extra forms for the applicant:

#### `GET /api/v1/related/pending/`

Lists pending related forms for the signed-in user (parent submission must be theirs).

#### `GET /api/v1/related/<access_token>/schema/`

Same shape as `GET /api/v1/forms/<form_id>/schema/`, plus optional `related` context (`parent_form_title`, `parent_reference_token`).

#### `POST /api/v1/related/<access_token>/submit/`

Same multipart rules as `POST /api/v1/forms/<form_id>/submit/`.

Published forms list example:

```json
{
  "ok": true,
  "forms": [
    {
      "id": 1,
      "title": "Leave request",
      "slug": "leave",
      "description": "…",
      "entity": { "id": 1, "slug": "default", "name": "Default" },
      "category": null,
      "submission_deadline": "2026-12-31",
      "submission_deadline_label": "Dec 31, 2026",
      "is_for_public": true,
      "layout_direction": "rtl",
      "public_url": "https://default.example.com/f/leave/",
      "intro_page_enabled": true,
      "intro_page_url": "https://default.example.com/f/leave/"
    }
  ]
}
```

When `intro_page_enabled` is true, `intro_page_url` is the public announcement page. Mobile apps show **Read more about this form** and open a native announcement screen (see below); tapping the row still opens the native submit screen.

### `GET /api/v1/forms/<form_id>/intro/`

Returns the full announcement page for native UI (headline, tagline, HTML message, gallery, schedule, where, contact, registration fee/capacity, video, brochure URL, apply label/URL). `highlights` / `guidelines` are line-based lists; `highlights_list_style` and `guidelines_list_style` are `bullet` (default) or `ordered`. Share fields: `share_url`, `share_mailto`, `share_whatsapp`, `qrcode_url` (public PNG). Requires bearer token and the same access rules as the published forms list. Returns `404` with `intro_disabled` when the announcement page is off.

### `GET /api/v1/inbox/?limit=50&offset=0`

Workflow inbox items (assignee or delegate). Each item includes `can_act`, `current_step_id`, and `manage_url` (studio browser fallback).

### `GET /api/v1/inbox/<submission_id>/`

Full inbox request detail for the native detail screen:

- `submission` — metadata (`reference_token`, workflow state, submitter, `can_act`, `acting_as_delegate`, `current_step_id`, nested `form`, etc.)
- `values` — field label + `display_value`; file fields include `value_id` and `attachment` (`filename`, `download_url`, `api_path`)
- `events` — workflow timeline (kind, author, message, step)
- `thread` — optional message thread (`messages`, `can_post`, `max_body_length`)
- `documents` — merged print template + submission document attachments (see below)

Requires bearer token; user must be inbox-visible for that submission (assignee or delegate).

#### `documents` block (inbox detail)

```json
{
  "documents": {
    "merged": {
      "has_merge_output": true,
      "can_view_pdf_inline": true,
      "show_docx_download": true,
      "show_odt_download": false,
      "show_pdf_download": true,
      "pdf_api_path": "/api/v1/inbox/42/documents/merged/pdf/",
      "docx_api_path": "/api/v1/inbox/42/documents/merged/docx/",
      "odt_api_path": "/api/v1/inbox/42/documents/merged/odt/"
    },
    "attachments": [
      {
        "id": 7,
        "title": "Contract",
        "filename": "contract.docx",
        "is_pdf": false,
        "can_preview_pdf": true,
        "download_api_path": "/api/v1/inbox/42/documents/attachments/7/",
        "pdf_api_path": "/api/v1/inbox/42/documents/attachments/7/pdf/"
      }
    ]
  }
}
```

- **Merged PDF inline:** `GET …/documents/merged/pdf/?inline=1` returns `application/pdf` for in-app preview when LibreOffice merge is available.
- **Merged DOCX/ODT:** `GET …/documents/merged/docx/` or `…/odt/` — download; mobile apps may preview DOCX via QuickLook (iOS) or an external viewer (Android).
- **Attachment download:** `GET …/documents/attachments/<id>/`
- **Attachment PDF preview (DOCX/ODT/etc.):** `GET …/documents/attachments/<id>/pdf/` — server converts to PDF when LibreOffice is installed (`can_preview_pdf`).

All document routes require the same bearer token and inbox visibility as the detail endpoint.

#### `POST /api/v1/inbox/<submission_id>/thread/post/`

Post a message on the submission thread (same visibility as detail). Body:

```json
{ "body": "Your message" }
```

Success returns the full inbox detail payload (updated `thread`). Posting marks the thread read for the user.

#### `GET /api/v1/inbox/<submission_id>/values/<value_id>/attachment/`

Download a file field attachment with bearer auth (alternative to the signed `download_url` on each value).

### `POST /api/v1/inbox/<submission_id>/workflow/`

Approve or reject when `submission.can_act` is true. Request body:

```json
{
  "decision": "approve",
  "comment": null,
  "workflow_action_anchor": 12
}
```

For `decision: "reject"`, `comment` is required (non-empty, max 800 chars). `workflow_action_anchor` must match `current_step_id` (stale-step protection).

Success returns the same shape as `GET …/inbox/<id>/` (updated submission + timeline). Errors use `ok: false` and `message`.

### `GET /api/v1/signatures/`

List the signed-in user’s signature images (same data as `/account/signatures/`).

### `POST /api/v1/signatures/`

Upload a new signature (`multipart/form-data`):

- `image` — PNG (or other allowed image type)
- `label` — optional

### `POST /api/v1/signatures/<id>/image/`

Replace an existing signature image (same multipart fields; `image` required).

### `POST /api/v1/signatures/<id>/primary/`

Set which signature is primary for merged documents.

### `DELETE /api/v1/signatures/<id>/`

Remove a signature.

### `GET /api/v1/submissions/search/`

Search submissions related to the signed-in user (same scope as studio submission search):

- Submissions you **submitted** (account or matching email)
- **Assignee** / delegate inbox items
- **Workflow** participation (timeline actions, thread messages)

Query parameters:

| Param | Values |
|-------|--------|
| `q` | Keywords (form title, slug, submitter, reference token) |
| `relation` | `any` (default), `applicant`, `workflow` |
| `workflow_state` | `in_progress`, `completed`, `rejected` |
| `form` | Form id |
| `limit` / `offset` | Pagination (default 50) |

Each item matches the inbox list shape plus `role_labels` (e.g. `Applicant`, `Assignee`, `Workflow`). Open detail with `GET /api/v1/inbox/<id>/`.

Mobile apps use the same detail endpoint after native form submit (`submission.id` in the submit response) so applicants and staff stay in-app instead of opening `detail_url` in a browser.

## Push devices

Register APNs / FCM tokens so the server can notify the user (inbox assignment, thread reply, pending related forms).

### `POST /api/v1/devices/register/`

Requires bearer token. Body:

```json
{
  "platform": "ios",
  "token": "<device-push-token>",
  "device_id": "<optional-vendor-id>"
}
```

`platform` is `ios` or `android`.

### `POST` or `DELETE /api/v1/devices/unregister/`

Deactivate token(s) for the signed-in user. Optional body `{ "token": "…" }` to remove one device; omit to deactivate all.

Logout also deactivates push devices for that user.

Set `MOBILE_PUSH_ENABLED = True` and wire APNs/FCM in your deployment to deliver notifications (`magicforms/mobile_push.py`).

## Settings

- `MOBILE_API_TOKEN_TTL_SECONDS` — token lifetime (default 30 days).
- `MOBILE_PUSH_ENABLED` — when `True`, `notify_user()` targets registered devices (provider integration required).

## Deploy

Run migrations (`0057_mobile_auth_token`). No change to nginx beyond existing proxy to Django. Exclude `ios/` and `android/` from rsync if desired.
