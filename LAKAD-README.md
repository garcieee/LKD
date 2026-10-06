# Lakad

Walking navigation for Makati. It routes people around missing sidewalks and obstructions, turns their photos into reports, and gives the city a ranked fix-it queue. "Lakad" is a working name.

Smart Urban Living Hackathon · Makati City · Oct 6–7, 2026

## What's in this repo

| Folder | For | What it does | Stack |
|---|---|---|---|
| `lgu-dashboard/` | Makati LGU and MMDA staff | Ranked fix-it queue, report heatmap, status workflow, exports | React, Vite, TypeScript, mapbox-gl |
| `open-dashboard/` | Businesses and commuters | Open, read-only view of what is blocked, what is fixed and where traffic is heavy | React, Vite, TypeScript, mapbox-gl |
| `mobile/` | Commuters | Walkable routes, photo reports, "Still there?" prompts | Flutter, mapbox_maps_flutter |
| `server/` | All three | One API for routing, reports, traffic and exports | FastAPI, osmnx, JSON file store |

The three front ends call the same API, so a report from a phone and a Fixed click on the LGU dashboard change the same data.

## The map

- **Mapbox**, pinned on Makati. Every app opens on Makati and has a Reset to Makati button. The pin lives in one file per app: `config/makati.ts` in the dashboards, `lib/config/makati.dart` in the app.
- **TomTom** Traffic for the congestion layer.
- **OpenStreetMap** for streets and sidewalks, through osmnx on the server.
- **Feel:** a world-monitor-style layer dashboard (many data layers, each one a switch) with the clean floating-panel look of the two reference screenshots.

## UX rule: everything toggles

1. Every data layer is a switch. Each app has one layer registry that the layer panel, the floating toolbar and (on mobile) the layer sheet all read from. Add a layer once and its switch appears everywhere.
2. Every panel collapses: left nav, list, right detail, legend.
3. Every map has a Map ⇄ Satellite switch and a Reset to Makati button.
4. Switch states are remembered between visits.
5. Open dashboard: a Commuter ⇄ Business lens. A lens is a preset of layers and panels, not a different app.
6. Mobile: Fastest / Walkable / Accessible route modes.

## Start here

- [STRUCTURE.md](STRUCTURE.md): the folder tree and what lives where
- [SETUP.md](SETUP.md): what to download, which keys to get, how to run each app

Scaffold only until kickoff (Tue 1:00 PM). No feature logic before then, so the git history starts clean.

## Documentation

Match this table to the organizers' list of required documents.

| Document | Where | Status |
|---|---|---|
| Problem and users | This file | To do |
| Features and done tests | This file | To do |
| Technology, AI and API disclosure | Below | In progress |
| Validation (four assumption tests) | Below | To do |
| Setup and run | `SETUP.md` | Draft |
| API reference | `/docs` on the running server (FastAPI generates it) | Automatic |
| Backup demo video | To be added | To do |

## Technology, AI and API disclosure

Update at every progress check. Undisclosed tools are penalized.

| Part | What we use | Disclose as |
|---|---|---|
| Mobile app | Flutter (Dart), mapbox_maps_flutter, image_picker, geolocator, http, shared_preferences | Open-source framework and packages. Mapbox free tier |
| Dashboards | React, Vite, TypeScript, mapbox-gl | Open-source libraries. Mapbox free tier |
| Congestion | TomTom Traffic API | Third-party API, free-tier key |
| Place search and routing | OpenRouteService API, called by our server | Third-party API, free-tier key. The app's search text and an optional nearby point go to it through the server |
| Map data | OpenStreetMap through osmnx, and an Overpass snapshot of the MRT-3 and LRT-1 stations (server/data/transit/stations.geojson) | Open data (ODbL). Credit OSM |
| Transit routes and terminals | "PUV Routes in Makati" study (Ayala Land; SYSTRA Philippines, Makati BRT Study, 2025) from the hackathon's Makati Data Hub | Organizer-provided data, hackathon use only. Route names and terminals only; positions are looked up by name through OpenRouteService and checked by hand |
| API | FastAPI, networkx, a JSON file store | Open-source libraries |
| Image AI | CLIP (open_clip ViT-B-32), MediaPipe and OpenCV | AI models, open weights, run locally |
| AI coding assistants | Claude (Anthropic): repo scaffold and file structure | AI coding tool. Add every assistant anyone on the team uses |

## Validation

Four assumptions, tested for 15 minutes each at kickoff. Record the answers here. They become the pitch quotes.

| Assumption | Quick test | Pass mark | Result |
|---|---|---|---|
| Commuters accept a slightly longer route to stay on a sidewalk | Show 5 people two routes and ask which they would take | Most pick Walkable when it adds about 150 m or less | |
| Transfers are a real pain, not only the last mile | Ask the same 5 for their worst Makati transfer. Ask the MMDA/LGU mentor which hubs get pedestrian complaints | Named hubs and specific problems you can quote | |
| People will photograph problems if it leads to a fix | Ask whether they would snap a photo if the city fixed the spot | Most say yes and name a spot | |
| The city would act on crowd reports | Ask the mentor what makes a report actionable for staff | A list of required fields for the report form | |

## Commit rules

- Everyone commits under their own GitHub account. When pairing, the person typing commits and adds a `Co-authored-by:` line.
- Small commits with plain messages ("route card shows avoided distance"), at least one per person per check.
- One branch per feature, merged through short pull requests that another member approves.

## Credits

Map data © OpenStreetMap contributors (ODbL). Maps by Mapbox. Traffic data © TomTom.
