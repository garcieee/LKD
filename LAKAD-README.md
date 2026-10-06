# Lakad

Walking navigation and crowd reporting for Makati. Commuters pick a destination, get a walking route that steers around reported hazards, and photograph new problems in an AR camera view. The city sees those reports as a ranked ticket queue.

Smart Urban Living Hackathon · iACADEMY MPH · Oct 6–7, 2026 · Team **Lakad Kinetic Development**
Project documentation: [Google Doc](https://docs.google.com/document/d/1-KtQXQGzGgUjQvdE_HK4or0s5GL7DViF/)

## What works today

| Folder | What it does | Stack |
|---|---|---|
| `mobile/` | Map of Makati with TomTom traffic, your location, destination search, Fastest / Walkable / Accessible walking routes with hazard counts, transit hubs (PUV terminals, MRT-3, LRT-1), report pins, and an AR camera for geotagged photo reports | Flutter, mapbox_maps_flutter, camera, geolocator, sensors_plus |
| `dashboard/` | Ticket queue with status workflow (open → verified → assigned → fixed), photo detail, insights panel, traffic layer, predicted foot-traffic layer with a past and forecast view | React, Vite, TypeScript, mapbox-gl |
| `server/` | `/reports` CRUD and photos, `/geocode`, `/route/walk`, `/transit/hubs`, `/footfall` and `/footfall/series` (predicted foot traffic), `/health`. JSON file store in `db/` | FastAPI, OpenRouteService |

Both clients use the same API, so a phone report and a dashboard status change hit the same data. Unresolved reports become no-go zones for Walkable and Accessible routes. Full API reference: `/docs` on the running server.

## Not built yet

"Still there?" verification, exports, barangay leaderboard, heatmap, satellite toggle, face blur, CLIP tagging. Their files are empty stubs. Layer state is not persisted. No auth on the API.

## Foot traffic is predicted, not measured

**Every foot-traffic number in Lakad is a prediction built from research and assumptions. Nothing is counted.** There are no cameras, sensors or phone data behind it. The dashboard says so on the layer, the forecast panel and the API (`kind: "estimate"`, `history_source: "simulated"`).

| What you see | What it really is |
|---|---|
| **Live** layer (Foot traffic panel) | The model's estimate for the current hour in Manila, refreshed as the clock moves. "Live" means it follows the clock, not that sensors feed it. |
| Map heat and the district ranking | A relative 0–100 index. 100 is the strongest hub at its busiest hour. It is not a head count. |
| **Past** in the Forecast panel | Simulated. The model's value for that weekday and hour, times a seeded day factor (rain days about 22% quieter, paydays about 8% busier) and ±5% hourly jitter. The same request gives the same series every time. |
| **Future** in the Forecast panel | A seasonal forecast of that simulated past: the average of the last four weeks at each hour of the week, scaled by recent activity that fades back over about a day, with an 80% range that widens further out. |
| "Typical miss" | Error from forecasting the last simulated week using the three before it. It scores the forecast against simulated data, so it says nothing about accuracy against real crowds. |

**How the index is built** (`server/app/services/footfall.py`, `server/data/footfall/hotspots.json`)

1. Each transit hub scores by what serves it: rail 5, P2P bus 1.5, city bus 1.2, jeepney 1, UV Express 1. Weights are our judgement.
2. A hub also gets a share (capped) of its district's route ends, counted from the organizer's "PUV Routes in Makati" data. Ayala is an end point of 9 routes, the most by far (the 56 routes have 112 end points).
3. Ten districts (Ayala CBD, Salcedo, Legazpi, Buendia, LRT-1 Gil Puyat, Guadalupe/Rockwell, Washington, Libertad, Poblacion, Makati Medical) add an anchor for demand transit data cannot see: offices, nightlife, markets, a hospital. Anchors are our estimates; each carries a `basis` note. The Salcedo, Legazpi, Poblacion and Rockwell anchors rest on general knowledge, not on a source we checked.
4. Hourly profiles (commuter, CBD, nightlife, weekend market, medical) multiply the score by time of day. The peaks and widths are assumptions, not measurements.
5. A modest uncertainty band (±25%) is attached to every value. It is a placeholder, not a fitted interval.

Research behind the assumptions: Makati's daytime population of roughly 3.2–4.2 million and about 800,000 workers (secondary sources), MRT Ayala/Buendia carrying about 200,000 daily commuters, Ayala's 1,100 m elevated walkway, and the Buendia pedestrian overpass. These are cited as approximate in `hotspots.json` and are not inputs to any formula.

**Known limits.** Route data has end points only, with no stop order or geometry. Several terminal positions are uncertain by 100–140 m. The index ignores weather, events and holidays except for the simulated rain and payday days. Do not quote the values as people per hour.

### Going live later: recommended approach

When real footage is available, replace the estimate with counts. The server already takes this shape: the estimator, `/footfall` and `/footfall/series` stay as they are, and measured counts take over per zone (`kind: "measured"`, `history_source: "measured"`). The best approach at present:

1. **Detect with NVIDIA LocateAnything.** It is an open vision-language detector (LocateAnything-3B, released June 2026) that finds objects from a text prompt, so a prompt such as "pedestrians" or "vehicles and pedestrians" needs no retraining to start. It decodes all boxes in one pass, which makes it fast enough for video.
2. **Classify the detections.** Run a small classifier on each detected crop for the project's labels (pedestrian, car, truck, bus, jeepney, motorcycle), trained on the Makati traffic dataset. This corrects the detector where Philippine vehicles, jeepneys above all, differ from its general training data.
3. **Count, don't track people.** Count line crossings and zone occupancy per camera and per time bucket, send only the counts to the server, and discard frames. This keeps privacy simple and matches the schema the dashboard already reads.
4. **Calibrate.** Fit the district weights and hourly profiles to the measured counts and report the real error. The simulated history is then replaced by measured history and the same forecaster runs on it.

Caveats: we have not run LocateAnything in this project. Its license (NVIDIA License) was reported as covering academic and non-profit research use, with commercial use not granted, so confirm the terms before any deployment beyond research. Expect to need a GPU; community reports describe a 4-bit build fitting an 8 GB Jetson, which we have not tested.

Sources: [LocateAnything release coverage](https://aiweekly.co/alerts/nvidia-locateanything-ships-open-at-10x-rival-speed), [model overview](https://comfyui-wiki.com/en/news/2026-06-29-nvidia-locateanything-3b-open-source-grounding-model), [model card summary and license](https://mixpeek.com/model/nvidia/LocateAnything-3B).

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
| Foot-traffic estimate and forecast | Our own rules, mode weights and hourly curves, plus a seasonal forecast, in plain Python. No machine-learning model and no scraped data. Inputs: the organizer's transit files and our curated district list | Predicted from assumptions and research, not measured. See "Foot traffic is predicted, not measured" |
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
