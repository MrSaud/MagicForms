# MagicForms iOS (SwiftUI)

Native iOS client for the MagicForms mobile API (`/api/v1/...` on the **main domain**).

## Requirements

- Xcode 15+ (iOS 17 deployment target)
- MagicForms backend running with migration `0057_mobile_auth_token` applied

## Open the project

```bash
cd ios
python3 generate_xcode_project.py   # if MagicFormsMobile.xcodeproj is missing
open MagicFormsMobile.xcodeproj
```

Alternatively, if you have [XcodeGen](https://github.com/yonaskolb/XcodeGen) installed:

```bash
cd ios && xcodegen generate
```

Select the **MagicFormsMobile** scheme and run on Simulator or a device.

## API base URL (build time only)

End users are **not** asked for a server URL. You set it once in Xcode:

**MagicFormsMobile** target → **Build Settings** → `API_BASE_URL`

| Configuration | Typical value |
|---------------|----------------|
| Debug | `http://127.0.0.1:8000` (Simulator + Django on the same Mac) |
| Release | `https://your-main-domain.example` (main site host for `/api/v1/...`) |

For Debug on a **physical device**, change Debug’s `API_BASE_URL` to your Mac’s LAN IP (e.g. `http://192.168.1.42:8000`) and run `runserver 0.0.0.0:8000`.

## Auth & home

1. Sign in with **organization username** (`org-slug` + `username`) and password.  
2. **Home** lists published forms (tap opens the form in Safari).  
3. **Inbox** (tray icon) shows workflow requests with a badge count.  
4. **Menu** (hamburger) — profile, studio links, refresh, sign out.  

See [docs/MOBILE_API.md](../docs/MOBILE_API.md) for API paths.

See [docs/MOBILE_API.md](../docs/MOBILE_API.md) for request/response shapes.

## Local backend

```bash
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Use a staff or portal-linked account allowed by `user_may_use_mobile_api`.
