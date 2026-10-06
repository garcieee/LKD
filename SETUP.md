# Setup

## Install

- Git, Node.js LTS (22 or 24), Python 3.11
- Mobile only: Flutter stable with Dart 3.13.5 or newer (`mobile/pubspec.yaml` needs it; Flutter 3.47.6 ships it), Android Studio with SDK and command-line tools, then `flutter doctor --android-licenses`. Android only, no iOS.

## Keys

| Service | Get it at | Variable |
|---|---|---|
| Mapbox public token (`pk.`) | account.mapbox.com | `VITE_MAPBOX_TOKEN` (dashboard), `MAPBOX_TOKEN` (`mobile/env.json`) |
| Mapbox downloads token (`sk.`, DOWNLOADS:READ) | account.mapbox.com | `MAPBOX_DOWNLOADS_TOKEN` in `~/.gradle/gradle.properties`, only if Gradle asks. Never in the repo |
| TomTom key | developer.tomtom.com | `VITE_TOMTOM_API_KEY` (dashboard), `TOMTOM_API_KEY` (`mobile/env.json`) |
| OpenRouteService key | openrouteservice.org | `ORS_API_KEY` in `server/.env` only. Powers search and routes |

Copy each template and fill it in. The copies are git-ignored.

```bash
cp dashboard/.env.example dashboard/.env.local
cp mobile/env.example.json mobile/env.json
cp server/.env.example server/.env
```

`localhost` only works on the laptop running the server. From a phone, or a dashboard opened on another device, set `API_BASE_URL` / `VITE_API_BASE_URL` to the laptop's LAN IP (`http://192.168.x.x:8000`) and add the dashboard origin to `CORS_ORIGINS` in `server/.env`.

## Run

**Server**

```bash
cd server
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --reload
pytest
```

Check from the phone's browser: `http://<laptop-ip>:8000/health` returns `{"ok": true}`. Test a report without the phone:

```bash
curl -F photo=@photo.jpg -F category=pothole -F lat=14.5547 -F lng=121.0244 http://localhost:8000/reports
```

**Dashboard**

```bash
cd dashboard
npm install
npm run dev -- --host      # also: npm test, npm run build, npm run lint
```

**Mobile**

```bash
cd mobile
flutter pub get
flutter test
flutter run --dart-define-from-file=env.json     # debug build, hot reload (r), restart (R)
flutter build apk --release --dart-define-from-file=env.json
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

`adb` lives in `<Android SDK>/platform-tools`; add it to your PATH. Enable USB debugging on the phone (tap Build number 7 times, then Developer options).

Notes: the Android project is committed, so don't run `flutter create`. The manifest allows cleartext HTTP to the laptop API and asks for camera and location. Android 15 devices may use 16 KB memory pages; `mapbox_maps_flutter` ships a compatible build.
