# Deploy MagicForms

Paths on the server assume the app lives at `/var/www/magicforms/`. Adjust service names if your host differs.

## 1. Sync code from your Mac

`config/settings.py` is **excluded** so production settings on the server are not overwritten.

```bash
rsync -avz \
  -e "ssh -i /Users/dev-saud/desktop/swapsec/swapKey.pem" \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude 'ios/' \
  --exclude 'android/' \
  /Users/dev-saud/Desktop/DjangoLab/MagicForms/ \
  ec2-user@ec2-18-198-36-222.eu-central-1.compute.amazonaws.com:/var/www/magicforms/
```

## 2. Update the app on the server

SSH in:

```bash
ssh -i /Users/dev-saud/desktop/swapsec/swapKey.pem \
  ec2-user@ec2-18-198-36-222.eu-central-1.compute.amazonaws.com
```

Then run:

```bash
cd /var/www/magicforms

# Virtualenv (create once: python3 -m venv .venv)
source .venv/bin/activate

# Dependencies (after requirements.txt changes)
pip install -r requirements.txt

# Database
python manage.py migrate --noinput

# Arabic/English translations (after locale/*.po changes)
python manage.py compilemessages

# Static CSS/JS (required after CSS/JS changes; nginx serves staticfiles/)
# theme.css is generated: edit magicforms/static/magicforms/css/src/*.css locally and run
#   python scripts/build_theme_css.py
# before syncing (the test suite fails if theme.css is stale).
python manage.py collectstatic --noinput

# Restart app (use your unit name if different)
sudo systemctl restart magicforms
sudo systemctl status magicforms --no-pager
```

Or run the update steps over SSH from your Mac (after rsync):

```bash
ssh -i /Users/dev-saud/desktop/swapsec/swapKey.pem \
  ec2-user@ec2-18-198-36-222.eu-central-1.compute.amazonaws.com << 'EOF'
set -e
cd /var/www/magicforms
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py compilemessages
python manage.py collectstatic --noinput
sudo systemctl restart magicforms
sudo systemctl reload nginx
EOF
```

## 3. First-time server setup (once)

On the EC2 instance:

```bash
sudo mkdir -p /var/www/magicforms
sudo chown ec2-user:ec2-user /var/www/magicforms

cd /var/www/magicforms
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy production `config/settings.py` to the server (rsync skips it). Set at least:

- `DEBUG = False`
- `ALLOWED_HOSTS` — e.g. `swapforms.com,.swapforms.com,www.swapforms.com`
- `MAGIFORM_BASE_DOMAIN` — `swapforms.com` (entity portals: `{entity.slug}.swapforms.com`; required for apex/default-entity routing; unregistered subdomains are blocked even when inferred from `ALLOWED_HOSTS` / the request host)
- `SECRET_KEY` (environment variable `DJANGO_SECRET_KEY` is supported)
- MySQL/MariaDB via `MYSQL_*` environment variables if used

**DOCX/ODT in-page preview (submission “Read document”):** the browser iframe shows a **PDF**, not Word. DOCX templates are merged server-side, then converted with **LibreOffice** (`soffice`). Locally you likely have LibreOffice installed; on the server you must install it too or only **Download DOCX** appears.

**Amazon Linux 2023 (EC2):** `dnf install libreoffice-headless` often does **not** place binaries under `/usr/lib64/libreoffice/`. If `ls` shows “No such file”, LibreOffice is **not installed** (or only a broken script exists). Use the [official AL2023 LibreOffice tutorial](https://docs.aws.amazon.com/linux/al2023/ug/al2023-libreoffice.html): download the Linux RPM bundle from [libreoffice.org](https://www.libreoffice.org/download/download-libreoffice/), then:

```bash
uname -p   # x86_64 or aarch64
cd /tmp
# Example — replace VERSION/ARCH with current stable from libreoffice.org
wget "https://download.documentfoundation.org/libreoffice/stable/25.2.5/rpm/x86_64/LibreOffice_25.2.5_Linux_x86-64_rpm.tar.gz"
tar zxvf LibreOffice_25.2.5_Linux_x86-64_rpm.tar.gz
cd LibreOffice_25.2.5.5_Linux_x86-64_rpm/RPMS
sudo dnf install -y ./*.rpm

# Verify — path is usually under /opt, not /usr/lib64:
find /opt -name soffice 2>/dev/null
libreoffice --version
```

Set systemd to that **real** binary (example):

```ini
Environment=MAGIFORM_SOFFICE=/opt/libreoffice25.2/program/soffice
```

Use the path from `find /opt -name soffice` on your instance (version folder name varies). Use **`program/soffice`**, not `soffice.bin` — the first headless run can exit with code **81** when using `.bin` alone; the `soffice` launcher retries automatically.

**RHEL / Fedora / older Amazon Linux** (when packages do install under `/usr`):

```bash
sudo dnf install -y libreoffice libreoffice-headless
ls -l /usr/lib64/libreoffice/program/soffice
MAGIFORM_SOFFICE=/usr/lib64/libreoffice/program/soffice
```

**Debian/Ubuntu:** `sudo apt install -y libreoffice-writer-nogui`

**Do not** rely on a lone `/usr/local/bin/libreoffice` script copied into the app tree — it fails under gunicorn (`dirname: command not found`, `oosplash` in `/var/www/magicforms`). Remove that and install LibreOffice properly.

If `soffice` is not on `PATH` for the `magicforms` service user, set `MAGIFORM_SOFFICE` to the full path from `find /opt -name soffice` or `/usr/lib64/.../program/soffice`, then restart the service.

Then `sudo systemctl restart magicforms`. PDF-primary print templates work without LibreOffice; DOCX/ODT templates need it for inline view.

If `check_libreoffice` shows `runs=True` but **Test conversion failed**, the app was likely calling `program/soffice` without `LD_LIBRARY_PATH` — deploy the latest `print_merge.py` (it sets that automatically) and re-run the check.

**In-page preview still blank after install?** The UI embeds a **PDF** (merged DOCX → PDF). Common causes:

1. **Gunicorn cannot see `soffice`** — installing LibreOffice for your SSH user is not enough. The `magicforms` systemd service needs the binary on `PATH` or:

   ```ini
   Environment=MAGIFORM_SOFFICE=/usr/lib64/libreoffice/program/soffice
   ```

2. **Headless LibreOffice needs a writable profile** — the app sets `HOME`/`TMPDIR` under `/tmp` for each conversion. If conversion still fails, run on the server (as the same user as gunicorn):

   ```bash
   cd /var/www/magicforms && source .venv/bin/activate
   python manage.py check_libreoffice
   ```

   You should see `runs=True` for one candidate and `Test conversion OK`. If not, fix the reported path or permissions, then `sudo systemctl restart magicforms`.

3. **Open the preview URL directly** — in the browser devtools Network tab, the iframe loads something like `…/s/<token>/merged/pdf/?inline=1`. Status **200** + `application/pdf` = good; **400** + plain text = merge or LibreOffice error (message in response body).

4. **Download DOCX works but preview does not** — merge succeeded; only PDF conversion failed. Focus on `check_libreoffice` and `MAGIFORM_SOFFICE`.

**Arabic in exported PDFs** (timeline, responses grid): bundled **Noto Sans Arabic** fonts live under `magicforms/fonts/`. After deploy, run `pip install -r requirements.txt` (adds `arabic-reshaper` and `python-bidi` for correct letter shaping). Ensure `magicforms/fonts/*.ttf` is included in your rsync/deploy.

Optional — Studio AI (form-from-text, inbox assistant), set in the server environment (read in `config/settings.py`):

- `OPENAI_API_KEY` — leave unset for keyword/heuristic fallbacks only
- `OPENAI_API_BASE` — default `https://api.openai.com/v1`
- `MAGIFORM_TEXT_TO_FORM_MODEL` / `MAGIFORM_INBOX_AI_MODEL` — default `gpt-4o-mini`

**Entity subdomains:** each active organization’s `slug` is the subdomain label. Example: entity slug `mosa-kuwait` → `https://mosa-kuwait.swapforms.com/`. **`https://swapforms.com/`** loads the **default** entity portal (entity slug `default`, override with `MAGIFORM_DEFAULT_ENTITY_SLUG`). An unregistered subdomain (no matching active organization slug) returns a 404 error page. Legacy paths `/e/<slug>/…` redirect to short URLs. Studio (`/manage/`) is served on the main URLconf on any host, e.g. `https://swapforms.com/manage/` or `https://default.swapforms.com/manage/`. Sign-in and Studio links on an entity subdomain stay on that host (they do not force `swapforms.com`).

Optional (recommended): share login between apex and subdomains:

```python
SESSION_COOKIE_DOMAIN = ".swapforms.com"
CSRF_COOKIE_DOMAIN = ".swapforms.com"
```

DNS: wildcard `*.swapforms.com` → your server; nginx `server_name` should accept `swapforms.com`, `www.swapforms.com`, and `*.swapforms.com`.

**nginx** must pass the **browser** hostname to Django. If `Host` is hard-coded to `swapforms.com`, every subdomain (`fff.swapforms.com`, etc.) will incorrectly show the **default** organization.

Copy the example config and edit SSL paths:

```bash
sudo cp /var/www/magicforms/deploy/nginx-swapforms.conf.example /etc/nginx/conf.d/magicforms.conf
sudo nginx -t && sudo systemctl reload nginx
```

Inside the `location /` block that has `proxy_pass` (all three host lines are required — Django uses `X-Forwarded-Host` when `USE_X_FORWARDED_HOST` is on):

```nginx
proxy_set_header Host $host;
proxy_set_header X-Portal-Host $host;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
```

**Remove** any line like `proxy_set_header Host swapforms.com;` or `proxy_set_header X-Forwarded-Host swapforms.com;` — that drops the subdomain on the first redirect.

Copy `deploy/nginx-swapforms.conf.example` if needed.

Verify on the server (should print `fff`, not `swapforms.com`):

```bash
curl -s -H "Host: fff.swapforms.com" http://127.0.0.1:8000/ -o /dev/null -w "%{http_code}\n"
# Expect 404 after app code is deployed

curl -s -H "Host: fff.swapforms.com" -H "X-Portal-Host: fff.swapforms.com" http://127.0.0.1:8000/ -o /dev/null -w "%{http_code}\n"
# Expect 404
```

Set `USE_X_FORWARDED_HOST = True` and `SECURE_PROXY_SSL_HEADER` in production `config/settings.py` (see repo `config/settings.py`).

In `TEMPLATES` → `context_processors`, include (required for entity subdomains):

```python
"magicforms.context_processors.portal_studio_urls",
```

Run migrations, then configure **systemd** + **gunicorn** (example unit name `magicforms.service`) and **nginx** to proxy to the WSGI app (`config.wsgi:application`).

**Outbound POST (external integrations):** install `cryptography` from `requirements.txt`. Process the delivery queue every minute:

```bash
* * * * * cd /var/www/magicforms && /var/www/magicforms/.venv/bin/python manage.py process_outbound_deliveries >> /var/log/magicforms-outbound.log 2>&1
```

Optional in production `config/settings.py`: `OUTBOUND_WEBHOOK_FERNET_KEY` (dedicated encryption key; defaults to `SECRET_KEY`). For local debugging only: `OUTBOUND_PROCESS_INLINE = True` runs each queued delivery immediately after submit/workflow (not recommended under gunicorn multi-worker).

**File fields in outbound POST:** mapped uploads are sent as a **signed download URL** (not raw file bytes). Set `MAGIFORM_OUTBOUND_FILE_BASE_URL = "https://swapforms.com"` so links in JSON use the public site host. Optional `OUTBOUND_FILE_URL_MAX_AGE = 3600` (seconds, default 1 hour).

## Mobile API

After deploy, run migrations so `MobileAuthToken` exists. Auth endpoints live at `/api/v1/auth/…` on the main host (see `docs/MOBILE_API.md`). Optional: `MOBILE_API_TOKEN_TTL_SECONDS` in production `config/settings.py`.

## Static files (CSS / JS)

Production **nginx** serves `/static/` from `staticfiles/` (see `deploy/nginx-swapforms.conf.example`), not from `magicforms/static/` in the repo.

- **Local** `runserver` reads `magicforms/static/` directly, so CSS changes show up immediately.
- **Production** needs `python manage.py collectstatic --noinput` after you change `theme.css` or other static assets, then reload nginx if needed.

If a layout fix works locally but not on swapforms.com, run collectstatic on the server and hard-refresh the browser (or bypass cache once).

## Media files (uploads — form logos, print templates, attachments)

Form header logos, organization logos, submission uploads, and print templates are **not** static files. They live under `media/` (default: `/var/www/magicforms/media/`).

- **Local:** with `DEBUG=True`, Django serves `/media/` itself (`config/urls.py`).
- **Production:** with `DEBUG=False`, Django does **not** serve `/media/`. **nginx must** (see `location /media/` in `deploy/nginx-swapforms.conf.example`).

If logos work on your Mac but show broken images on swapforms.com, check:

1. **nginx** — production config includes:

   ```nginx
   location /media/ {
       alias /var/www/magicforms/media/;
   }
   ```

   Then `sudo nginx -t && sudo systemctl reload nginx`.

2. **Directory and permissions** — uploads must exist and nginx must be able to read them:

   ```bash
   sudo mkdir -p /var/www/magicforms/media
   sudo chown -R ec2-user:ec2-user /var/www/magicforms/media
   # If nginx runs as ``nginx``, allow read:
   sudo chmod -R o+rX /var/www/magicforms/media
   ```

   Logos are stored at `media/form_logos/<form_id>/…`. After uploading in Studio on the **server**, confirm a file exists there.

3. **Do not use `collectstatic` for logos** — that only copies CSS/JS into `staticfiles/`. Uploads are separate.

4. **rsync deploy** — syncing code from your Mac does **not** copy files you uploaded locally. Upload logos again in Studio on the server, or rsync `media/` separately if you intentionally mirror dev uploads.

5. **Quick test** — open a broken logo URL in the browser (right‑click image → open in new tab). Expect `200` and an image. `404` → nginx path or missing file; `403` → permissions.

`MEDIA_ROOT` / `MEDIA_URL` in production `config/settings.py` should match the nginx `alias` path (`/media/` URL → `…/media/` on disk).

## 4. Logs / checks

```bash
sudo journalctl -u magicforms -n 50 --no-pager
curl -I http://127.0.0.1:8000/manage/login/   # if gunicorn binds locally
```

## Production settings changes (config/settings.py is not synced)

- 2026-09-15: add `"magicforms.middleware.SuperuserOrganizationScopeMiddleware"` to `MIDDLEWARE`
  right after `django.contrib.auth.middleware.AuthenticationMiddleware`. Super admins are sent to
  `/manage/choose-organization/` after sign-in until they pick an organization.
