# MagicForms Android (Jetpack Compose)

Native Android client with the same auth flow as the iOS app (`/api/v1/...` on the **main domain**).

## Requirements

- Android Studio Ladybug (2024.2+) or newer
- JDK 17
- MagicForms backend with migration `0057_mobile_auth_token` applied

## Open the project

```bash
cd android
# Open folder in Android Studio, or:
./gradlew :app:assembleDebug
```

## API base URL (build time only)

Set in `app/build.gradle.kts` → `buildTypes` → `buildConfigField("API_BASE_URL", ...)`:

| Build | Typical value |
|-------|----------------|
| **debug** | `http://10.0.2.2:8000` — emulator → Django on your Mac (`10.0.2.2` = host `127.0.0.1`) |
| **release** | `https://your-main-domain.example` |

**Physical device (debug):** use your Mac’s LAN IP, e.g. `http://192.168.1.42:8000`, and run `python manage.py runserver 0.0.0.0:8000`.

Cleartext HTTP is allowed only in debug (`usesCleartextTraffic`).

## Features (parity with iOS)

- Divided **organization username**: editable `org-slug` + `–` + `username`
- **Home** — published forms list (opens in browser)
- **Inbox** — workflow requests with badge on the tray icon
- **Hamburger menu** — profile, studio links, refresh, sign out
- Bearer token in **EncryptedSharedPreferences**

See [docs/MOBILE_API.md](../docs/MOBILE_API.md).

## Local backend

```bash
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```
