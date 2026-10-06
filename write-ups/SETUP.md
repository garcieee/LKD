# Setup

What to download, which keys to get, and how to run each app. Do this before kickoff. Scaffold only: no feature logic until Tue 1:00 PM.

## 1. Install on every machine

- Git and a GitHub account in the team org
- VS Code (add the Flutter and Dart extensions on the mobile laptops)
- Node.js current LTS, 22 or 24. Your plan says 20, but Node 20 reached end of life in April 2026
- Python 3.11 (server, in a virtual environment)

## 2. Install on the mobile developers' laptops

- Flutter SDK, stable channel. Run `flutter doctor` until it is clean
- Android Studio, latest stable. Install the SDK, platform tools and command-line tools
- Accept licenses: `flutter doctor --android-licenses`
- One debug build to warm the Gradle cache: `flutter build apk --debug`. Do not upgrade Flutter, Android Studio or Gradle during the event
- Two test phones with USB debugging on, debug build installed once, USB cables packed
- scrcpy on the demo laptop, mirroring tested

## 3. Accounts and keys

| Service | Get it at | Used for | Variable |
|---|---|---|---|
| Mapbox public token (`pk.`) | account.mapbox.com | The map in all three apps | `VITE_MAPBOX_TOKEN` in the dashboards, `MAPBOX_TOKEN` in `mobile/env.json` |
| Mapbox downloads token (`sk.`, scope DOWNLOADS:READ) | account.mapbox.com | Android build only. Create it only if Gradle asks for it | `MAPBOX_DOWNLOADS_TOKEN` in `~/.gradle/gradle.properties`. Never in the repo |
| TomTom API key | developer.tomtom.com | The congestion layer | `VITE_TOMTOM_API_KEY` in the dashboards, `TOMTOM_API_KEY` in `mobile/env.json` and `server/.env` |

At kickoff, ask the organizers whether the Mapbox and TomTom free tiers count as allowed. The rules ban paid services.

- If Mapbox is not allowed: switch to MapLibre with OpenFreeMap tiles, which needs no key.
- If TomTom is not allowed: remove `congestion` and `incidents` from each layer registry and their switches disappear everywhere.

## 4. Env templates

Every app has a committed template. Copy it, fill it in, and never commit the copy. All copies are git-ignored.

| Template | Copy to |
|---|---|
| `.env.example` (root) | Reference only. The master list of every variable |
| `lgu-dashboard/.env.example` | `lgu-dashboard/.env.local` |
| `open-dashboard/.env.example` | `open-dashboard/.env.local` |
| `mobile/env.example.json` | `mobile/env.json` |
| `server/.env.example` | `server/.env` |

```bash
cp lgu-dashboard/.env.example lgu-dashboard/.env.local
cp open-dashboard/.env.example open-dashboard/.env.local
cp mobile/env.example.json mobile/env.json
cp server/.env.example server/.env
```

On Windows PowerShell, use `Copy-Item` instead of `cp`.

`localhost` only works on the machine that runs the server. From a phone, or from a dashboard opened on another device, set the API URL to the laptop's hotspot IP, for example `http://192.168.x.x:8000`.

## 5. Generate the project files

The folders already exist with the structure in `STRUCTURE.md`. These commands add the Vite and Flutter project files around them.

**LGU dashboard**

```bash
cd lgu-dashboard
npm create vite@latest . -- --template react-ts   # non-empty folder prompt: choose "Ignore files and continue"
npm install
npm install mapbox-gl
npm run dev -- --host
```

**Open dashboard**: the same, but on its own port so both can run at once.

```bash
cd open-dashboard
npm create vite@latest . -- --template react-ts
npm install
npm install mapbox-gl
npm run dev -- --host --port 5174
```

`--host` lets other devices on the hotspot open the page. If TypeScript complains about missing mapbox-gl types, run `npm install -D @types/mapbox-gl`.

**Mobile app**

```bash
cd mobile
flutter create --platforms=android .
flutter pub add mapbox_maps_flutter http image_picker geolocator shared_preferences
flutter run --dart-define-from-file=env.json
```

In `android/app/src/main/AndroidManifest.xml`, set `android:usesCleartextTraffic="true"` on the `<application>` tag so the app can call the laptop over plain HTTP. If `flutter create` refuses to run in the existing folder, run it in a temporary folder and copy `android/`, `pubspec.yaml` and `lib/main.dart` across.

**Server**

```bash
cd server
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --reload
```

Your plan used `main:app`. The file is `app/main.py` here, so the command is `app.main:app`.

Test it from a phone on the team hotspot: `http://<laptop-ip>:8000/health` should return `{"ok": true}`. Do this first. A phone that cannot reach the laptop is the risk most likely to cost a progress check.

## 6. Big downloads (do these at home, venue wifi is unreliable)

- `npm install` in both dashboards and `pip install -r requirements.txt` in the server, so everything is cached.
- CLIP ViT-B-32 weights, several hundred MB. Run once to cache them:

```bash
python -c "import open_clip; open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k')"
```

- The Makati walking graph, saved as a backup file. This is map data, not feature code. osmnx drops sidewalk tags by default, so the first line matters.

```python
import osmnx as ox
ox.settings.useful_tags_way += ["sidewalk", "sidewalk:left", "sidewalk:right", "sidewalk:both", "footway", "foot"]
G = ox.graph_from_place("Makati, Metro Manila, Philippines", network_type="walk")
ox.save_graphml(G, "server/data/makati_walk.graphml")
```

The `.graphml` file is git-ignored. List it in the docs as a cached OpenStreetMap extract.

## 7. First 30 minutes after kickoff

- [ ] Push this scaffold as the first commit and have everyone clone it
- [ ] Everyone copies their env templates and fills in the keys
- [ ] A phone reaches `http://<laptop-ip>:8000/health` over the hotspot
- [ ] Agree the API response shapes. Write them into `server/` and each `src/types/api.ts`
- [ ] Ask the organizers: are Mapbox and TomTom free tiers allowed, and which checks are Milestones 1–3
- [ ] Ten minutes with the MMDA/LGU mentor on report fields (the five questions are in the plan)
- [ ] Issue board with the three features
- [ ] First feature work: Mapbox map pinned on Makati in the app and in the LGU dashboard
