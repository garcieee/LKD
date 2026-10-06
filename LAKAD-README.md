# Lakad

Walking navigation and crowd reporting for Makati. Commuters pick a destination, get a walking route that steers around reported hazards, and photograph new problems in an AR camera view. The city sees those reports as a ranked ticket queue.

Smart Urban Living Hackathon · iACADEMY MPH · Oct 6–7, 2026 · Team **Lakad Kinetic Development**
Project documentation: [Google Doc](https://docs.google.com/document/d/1-KtQXQGzGgUjQvdE_HK4or0s5GL7DViF/)

## What works today

| Folder | What it does | Stack |
|---|---|---|
| `mobile/` | Map of Makati with TomTom traffic, your location, destination search, Fastest / Walkable / Accessible walking routes with hazard counts, transit hubs (PUV terminals, MRT-3, LRT-1), report pins, and an AR camera for geotagged photo reports | Flutter, mapbox_maps_flutter, camera, geolocator, sensors_plus |
| `dashboard/` | Ticket queue with status workflow (open → verified → assigned → fixed), photo detail, insights panel, traffic layer | React, Vite, TypeScript, mapbox-gl |
| `server/` | `/reports` CRUD and photos, `/geocode`, `/route/walk`, `/transit/hubs`, `/health`. JSON file store in `db/` | FastAPI, OpenRouteService |

Both clients use the same API, so a phone report and a dashboard status change hit the same data. Unresolved reports become no-go zones for Walkable and Accessible routes. Full API reference: `/docs` on the running server.

## Not built yet

"Still there?" verification, exports, barangay leaderboard, heatmap, satellite toggle, face blur, CLIP tagging. Their files are empty stubs. Layer state is not persisted. No auth on the API.

## Run it

See [SETUP.md](SETUP.md).

## Technology, AI and API disclosure

| Part | Used | Disclose as |
|---|---|---|
| Mobile | Flutter, mapbox_maps_flutter, http, camera, geolocator, sensors_plus | Open source. Mapbox free tier |
| Dashboard | React, Vite, TypeScript, mapbox-gl | Open source. Mapbox free tier |
| Server | FastAPI, JSON file store | Open source |
| Traffic | TomTom Traffic flow tiles | Third-party API, free-tier key |
| Search and routing | OpenRouteService, called by our server | Third-party API, free-tier key. Search text and an optional nearby point go to it through the server |
| Map data | OpenStreetMap, incl. an Overpass snapshot of MRT-3 and LRT-1 stations (`server/data/transit/stations.geojson`) | Open data (ODbL). Credit OSM |
| Transit routes and terminals | "PUV Routes in Makati" study (Ayala Land; SYSTRA Philippines, Makati BRT Study, 2025), from the hackathon's Makati Data Hub | Organizer-provided, hackathon use only. Route names and terminals only; positions were looked up by name through OpenRouteService and checked by hand |
| AI coding assistant | Claude (Anthropic): scaffolding, code, tests, docs | Add every assistant anyone on the team uses |

## Validation

Four assumptions, 15 minutes each. Record results here; they become the pitch quotes.

| Assumption | Quick test | Pass mark | Result |
|---|---|---|---|
| Commuters accept a slightly longer route to stay on a sidewalk | Show 5 people two routes, ask which they would take | Most pick Walkable at about +150 m or less | |
| Transfers are a real pain, not only the last mile | Ask the same 5 for their worst Makati transfer; ask the MMDA/LGU mentor which hubs get complaints | Named hubs and quotable problems | |
| People will photograph problems if it leads to a fix | Ask if they would snap a photo if the city fixed it | Most say yes and name a spot | |
| The city would act on crowd reports | Ask the mentor what makes a report actionable | A list of required report fields | |

## Rules

- Everyone commits under their own GitHub account. Pairing: add a `Co-authored-by:` line.
- Small commits, one branch per feature, short pull requests.
- Never commit keys. `.env*` and `mobile/env.json` are git-ignored; copy the `*.example` files.
- Submission is due **Oct 7, 2026, 1:00 PM**: prototype, this repo merged to `main`, documentation, technology/API/AI/hardware lists, contribution record, demo materials.

Map data © OpenStreetMap contributors. Maps by Mapbox. Traffic data © TomTom.
