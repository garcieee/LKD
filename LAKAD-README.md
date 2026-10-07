# Lakad

Walking navigation and crowd reporting for Makati. Commuters pick a destination, compare walking routes that steer around reported hazards, pick a way to commute (walk, ride one PUV or train, walk), start the trip and are tracked along it, and photograph new problems in an AR camera view. The city sees those reports as a ranked ticket queue.

Smart Urban Living Hackathon · iACADEMY MPH · Oct 6–7, 2026 · Team **Lakad Kinetic Development**
Project documentation: [Google Doc](https://docs.google.com/document/d/1-KtQXQGzGgUjQvdE_HK4or0s5GL7DViF/)

## What works today

| Folder | What it does | Stack |
|---|---|---|
| `mobile/` | Map of Makati with TomTom traffic, your location, destination search, a guided trip (compare Fastest / Walkable / Accessible walking routes with hazard counts, then suggested commute routes with arrival time and the quickest marked, drawn leg by leg, then Start for live tracking with a navigation bar and a map that turns with the phone's heading, plus a compass chip), transit hubs (PUV terminals, MRT-3, LRT-1), report pins, an AR camera for geotagged photo reports (hazards and PWD accessibility barriers), and a hold-to-record SOS on the camera button | Flutter, mapbox_maps_flutter, camera, geolocator, sensors_plus |
| `dashboard/` | Ticket queue with status workflow (open → verified → assigned → fixed), photo detail, SOS tickets that top the queue, blink on the map and are sorted by who must respond (police, medical, fire and rescue), insights panel (including handler workload and SOS by responder), traffic layer, predicted foot-traffic layer with a past and forecast view, a Barangays menu with data that narrows to the picked barangay, and a map that dims everything outside Makati | React, Vite, TypeScript, mapbox-gl |
| `server/` | `/reports` CRUD and photos, `POST /sos` (video), `/geocode`, `/route/walk`, `/route/commute`, `/transit/hubs`, `/footfall` and `/footfall/series` (predicted foot traffic), `/health`. JSON file store in `db/` | FastAPI, OpenRouteService |
| `models/` | Ticketing rules: same-place matching, priority score, light note classification, with tests and an evaluation ([models/tickets/EVALUATION.md](models/tickets/EVALUATION.md)). The server loads them and runs them in its ticket loop (on by default; `TICKETS_SYNC=0` in `server/.env` turns it off), keeps the tickets in SQLite (`db/lakad.db`) and writes `ticket_id`, `district_id`, `priority` and `band` onto each report. The dashboard queue ranks by that priority, after SOS, and shows the band | Python standard library; the evaluation also uses numpy, scipy, scikit-learn |

Both clients use the same API, so a phone report and a dashboard status change hit the same data. Unresolved hazard reports become no-go zones for Walkable and Accessible routes; missing ramps, tactile paving and broken elevators only for Accessible. An SOS never does. Full API reference: `/docs` on the running server.

## Not built yet

"Still there?" verification, exports, barangay leaderboard, heatmap, satellite toggle, face blur, CLIP tagging. Their files are empty stubs. Layer state is not persisted. There are no accounts: anyone who can reach the API can use it, and anyone who can open the dashboard can triage.

## Reviewing new tickets: Confirm or Reject

A new ticket shows a review card at the top of its detail view. **Confirm** moves it to *Verified*, from where the stepper takes it on to Assigned and Fixed. **Reject** marks it *Rejected*: it disappears from the queue (unless *Show rejected* is on), the map, the Insights numbers, the phone's list and route avoidance, but stays on the server and can be reopened. Rejecting an SOS asks once more first. The queue header counts tickets still waiting for review. A change made on one row goes to its ticket, so every report of the same hazard follows. Nothing is deleted: a ticket fixed or rejected more than 30 days ago leaves the dashboard's list but stays in `db/lakad.db`. There is no sign-in: anyone who can open the dashboard can confirm or reject. A **note for the reporter** goes with the decision: rejecting needs a reason (the Reject button stays off until one is written), and Confirm and *Yes, mark resolved* take an optional note. The notes show in the ticket, and the reporter reads them in the phone's My tickets; the public list leaves them out.

## My tickets: the phone's tickets button

The ticket button at the top left of the phone's map opens **My tickets**: every report and SOS sent from this phone, newest first, each with its ID (`LKD-3F2A9C`, the same code the dashboard shows), its status in plain words (*Received, waiting for the city to review it*, *Confirmed by the city*, *Assigned to Ana Reyes*, *Resolved*, *Not accepted*) and the notes the city left: why a ticket was not accepted, what it said on confirming, what it said on the fix. Pull down to refresh. A ticket that changed since the person last looked is tagged **NEW**, and the button wears a red dot until they open the menu. Tapping a ticket opens its card.

There are no accounts, so the phone keeps the IDs of what it sent in its own storage (`shared_preferences`) and asks the server for their latest status with `GET /my-tickets?ids=` (up to 100 at a time). Knowing a ticket's ID is the proof it is yours, which is why an SOS and a rejected ticket come back here and nowhere in the public list. Limits: only tickets sent from this version on are remembered, and clearing the app's data or reinstalling forgets them; an offline phone shows the last status it knew and says it could not update. Anyone who has an ID can ask for that ticket.

**Told when the city updates a ticket.** While the app is open the phone asks about its tickets every 30 seconds, and at once when you come back to it. When the city confirms, assigns, resolves or does not accept a ticket, changes its handler or leaves a note, a banner over the map names it (*LKD-3F2A9C: Confirmed by the city*); tapping it opens that ticket, or My tickets when several changed together. Each change is announced once. Not announced: what changed while the app was closed (the red dot and NEW tag say that), anything while My tickets is open, and anything over the camera, which waits until you are back. With no remembered ticket the phone does not ask at all, and an offline phone asks again after twice the wait, up to five minutes, without a word.

**In the background.** The phone asks permission to show notifications once, right after the first ticket it sends. If allowed, a change found while the app is in the background becomes a notification (the ticket ID and its status, never the city's note) and the phone asks every 2 minutes then; if not, it stops asking until you come back. **These are local notifications, not push.** Nothing reaches a phone once Android has frozen or closed the app, which happens within minutes of leaving it, so a change made while the app is closed shows only as the red dot at the next launch. Real push needs Firebase and a server that pushes, and is not built. Delivery is up to 30 seconds late with the app open and 2 minutes in the background. A change is anything that moves the ticket's `updated_at` (status, handler, notes); `/my-tickets` already carried it, so the server is unchanged. The notification setup (`flutter_local_notifications`, the Android 13 permission, a notification icon) builds as an APK but **has not been run on a physical phone**, and there is no iOS project. Tests: `mobile/test/ticket_updates_test.dart`, `ticket_watch_test.dart`, `ticket_notice_test.dart`, and the `updated_at` test in `server/tests/test_notes.py`.

## Accessibility (PWD) reports

Next to the hazards, the report picker offers four barriers for persons with disability: **Missing or broken ramp** (including a crossing with no curb cut), **Blocked or missing tactile paving**, **Broken elevator or escalator** (at a station or overpass) and **Steep or broken sidewalk**. Each is a category like pothole: one per report, severity Medium, and its own ticket, joined only by reports of the same barrier nearby.

Unresolved ramp, tactile-paving and elevator reports are no-go zones for the **Accessible** route only. Fastest and Walkable ignore them and do not count them among the hazards a route passes: someone walking can step off a curb or take the stairs. A steep or broken sidewalk trips anyone, so Walkable steers around it too. An Accessible commute also skips a station with an open ramp, tactile-paving or elevator report at it (no-go zones never cover the ends of a walk). When the barriers box an Accessible route in, their zones are dropped first and the hazards' kept; only if that fails too does the route go without zones, and it then says so.

In the ticket rules (`models/tickets/`) the four have a danger value of 0.5, like a blocked sidewalk, note word lists in English and Filipino, and placeholder offices to confirm with the mentor. A note that names who a barrier stops ("pwd", "wheelchair") is not read as danger, so the wording alone does not move its rank. The SQLite tickets table takes them through a second migration, run when the server starts, that rebuilds the table and keeps every ticket, sighting and status change.

**Known limits.** The word lists were written by Claude from general knowledge and no native speaker has reviewed them. Bare "ramp" and "slope" are left out because Makati notes use them for flyover ramps. The note, ranking and matching evaluations cover the original six hazards only: there are no labelled notes or rater judgments for the PWD barriers, so their danger value is a judgement, not a fit. The Accessible route still rests on OpenRouteService's wheelchair profile, which knows little about Makati's ramps and curbs; crowd reports are what change it. A tactile-paving report reroutes the wheelchair route, which helps blind users only in part. The change is one-way: a server older than it answers 500 once a PWD report is stored, so remove those from `db/reports.json` before running one. Tests: `server/tests/test_route.py`, `server/tests/test_commute_route.py`, `server/tests/test_hazards.py`, `server/tests/test_ticket_sync.py`, `models/tickets/tests/test_storage.py`, `models/tickets/tests/test_engine.py`, `models/tickets/tests/test_classify.py`, `mobile/test/report_ui_test.dart`.

### Finding tickets: filters and ID search

The queue has a search box, status chips with counts, and a category dropdown. **Active** (the default) is everything still to do; **Unverified** is new tickets waiting for Confirm or Reject; **Verified** is confirmed tickets, verified or assigned to a handler; **Resolved** and **Rejected** are the rest. Searching by ID takes the code as shown (`LKD-3F2A9C`, in any case, with or without the dash) or just its first few characters. A search looks at every ticket whatever its status or category, so a resolved ticket is still found; picking a chip or a category leaves the search. Each ticket shows one urgency label, the ticket engine's band (Critical, High, Medium, Low), falling back to the category's severity until the engine has scored it. The urgent counts (the red Tickets dot and Insights) use the same rule: Critical or High.

### Ticket IDs, enlarging pictures, assigning a handler

Every ticket shows an ID like `LKD-3F2A9C` (the first six characters of the ticket's id, in capitals) in the queue and at the top of its detail view; all sightings of one hazard share it. Clicking a ticket's picture opens it large over the dashboard (Esc, the × or a click outside closes it) instead of a new tab.

After **Confirm**, the ticket asks who will fix it: pick a name from the roster (`dashboard/src/config/handlers.ts`, a demo list to replace with real staff) or choose *Someone else…* and type one. **Assign** moves it to *Assigned* and saves the name on the ticket (`handler`, up to 60 characters); the name then shows greyed out with a **Change** button that goes back to the pick. An assigned ticket asks *Is this ticket resolved?*, and **Yes, mark resolved** moves it to *Fixed*, where it shows who handled it and can be reopened. The status bars are display-only: the cards in the ticket move it, so a ticket cannot skip its handler. The server refuses a handler before a ticket is verified. Like everything else, this has no login, so the name is whatever the person at the dashboard picks.

## SOS: hold the camera button to call for help

**On the phone.** Tap the camera button for a photo report, as before. *Hold* it and the app switches to SOS mode: it records a silent video (up to 30 s) while the screen slowly turns red from the edges. Three arrows and an X above the button say *slide up to cancel*, and a banner says *SOS mode* with the clock. Slide up to the X and let go: the video is deleted and nothing is sent. Let go anywhere else: the video goes to the city at once, with no form in between. A clip under one second (a press of about a second and a half) is dropped with a hint. If the upload fails, the clip stays on screen with *Try again* until it is sent or discarded.

**At the city.** The SOS tops the Tickets queue as a red row, its pin blinks red on the map with a ripple, a red banner and a red Tickets button call for attention, and the ticket plays the video. Whoever watches it picks who must respond: **Police** (crime, violence or a threat), **Medical** (injury, collapse or illness) or **Fire and rescue** (fire, flood or someone trapped). Until then the row reads *SOS · Unsorted* and stays above the sorted ones; every open SOS stays above every hazard. Sorting does not change the status: the SOS moves through open, verified, assigned and fixed like any ticket, and the blinking stops when it is fixed. People who asked their system for reduced motion get a steady red instead of blinking.

**Server.** `POST /sos` takes the video (MP4, MOV or WebM, read from the bytes, up to 40 MB) and a location in Makati, and files an urgent `sos` ticket with a `video_url`. Clips are served from `/videos/`. `GET /reports` leaves SOS out unless asked (`include_sos=true`, which the dashboard does), so the public app's map and AR view never show where someone called for help. An SOS is never a no-go zone for routes. The dashboard sorts one with `PATCH /reports/{id}` and `{"sos_kind": "police" | "medical" | "fire_rescue"}`, which the server, the engine and `lakad.db` all refuse on a hazard. The SOS rules (never joined to another ticket, never scored: priority 100, band Critical) are in `models/ticket_sos/`, which the ticket engine calls. Tests: `server/tests/test_sos.py`, `models/ticket_sos/tests/test_sos.py`, `dashboard/src/features/queue/tickets.test.ts`, `mobile/test/sos_hold_test.dart`, and the SOS case in `mobile/test/api_contract_test.dart`, which uploads from the real phone client to a real server.

**Limits, stated plainly**
- **Video only, no sound, by design.** The microphone permission is stripped from the app. Recording other people's conversations is legally sensitive in the Philippines; get advice before enabling audio.
- **Nothing alerts a person.** The city sees an SOS only while the dashboard is open and polling every 10 seconds. There is no push, SMS or call to a responder, and no dispatch integration. Do not present this as an emergency service.
- **A person sorts every SOS.** Nothing reads the video, and the phone does not ask what happened. The kind tells the city whom to call; Lakad calls no one. One kind per SOS, and a sorted one can change kind but not go back to unsorted.
- **No accounts.** Anyone who can reach the API can file an SOS or list them. Hiding SOS from the public list is a convenience, not security. Put the dashboard and `include_sos` behind a login before anyone real depends on it. False alarms are limited only by the hold and the one-second minimum.
- **Needs a GPS fix inside Makati**, the same as a photo report, so it cannot start without one.
- **Hold-and-slide is hard for some people.** There is no alternative for screen-reader or switch users yet.
- **Clips sit unencrypted in `db/videos/` with no retention limit.** Treat the folder as sensitive. It is git-ignored, with the rest of `db/`.
- **Not run on a physical phone.** Verified with analyzer, widget and unit tests, and a real upload to a real server. The recording itself (camera plugin, Android recorder, haptics) needs a device test.

## Barangays: find one and zoom to it

The dashboard's sidebar has a **Barangays** entry between Map and Tickets. It opens a panel with a search box (a name in any spelling, such as `dasmarinas`, `belair` or `sta cruz`, or `district 2`), District 1 and 2 chips, and a list of Makati's 23 barangays with how many unresolved tickets each has (SOS and urgent ones called out), alphabetical or busiest first. Pick one, or press Enter on the best match, and the map zooms to it and tints it, and the tickets, pins and Insights narrow to it (below). **Show all of Makati** zooms back out and shows everything again. The panel's switch turns the outlines and names on the map on or off: with it on (the default), each barangay's name is drawn on the map while it is zoomed out, and fades away as the streets take over. Enter in the search picks the first match; Esc clears the search, then closes the panel; the barangay stays picked.

**Makati stands out.** Everything outside the city is dimmed and a soft shadow runs along its edge, so the city looks raised off the map. The edge is a solid dark line and the barangay borders are dark dashes, each with a white casing under it, drawn over the traffic and foot-traffic layers so they stay readable with those on. The dimming and the city edge are always on; the panel's switch only turns the barangay outlines and names on and off. The city's edge is worked out from the barangays themselves (the sides only one barangay has), so it needs no second boundary file; the small piece inside the city that belongs to no barangay is dimmed too: it is the Manila South Cemetery, which belongs to the City of Manila and which Makati's official boundary leaves out. Traffic is drawn only in Makati: the dashboard cuts TomTom's road lines at the city's edge (`dashboard/src/layers/clip.ts`), so a road that runs through the border stops at it. The phone's traffic layer is not clipped.

The outlines are the ones the ticket engine uses to give a ticket its district (`models/tickets/resources/districts.json`, OpenStreetMap contributors, ODbL). `dashboard/src/data/barangays.ts` is generated from that file by `python3 dashboard/scripts/build_barangays.py`, which also finds each name's spot, the point furthest inside the shape. A test fails if the two drift apart. There are 23, not Makati's former 33: the ten EMBO barangays are Taguig now. Tickets outside the 23 count in none.

**A picked barangay narrows the data.** While one is picked (the tint is the sign), the Tickets queue lists only its tickets and its status chips and header count only them, the map draws only its report pins, and Insights counts only its reports. A **Showing: Poblacion ✕** chip says so on the map, at the top of the queue and at the top of Insights; its ✕, like **Show all of Makati**, brings everything back and zooms out. The barangay stays picked when the panel closes (Insights takes its place in the dock), until cleared, and is forgotten on reload. A ticket is in the barangay its pin falls in, by the same rule as the counts in the list, so a count and the tickets behind it agree; a ticket outside the 23 is in none, so it is not shown while one is picked. **Searching by ticket ID ignores the barangay**, as it ignores status and category: the ID finds its ticket wherever it is, and the line under the filters then reads *Searching all of Makati, not just Poblacion*. A ticket opened from outside the barangay keeps its pin while it is open. **Left city-wide on purpose:** the Tickets button's count and red dot, the new-ticket toast and the SOS banner (a call for help must not be hidden by where someone is looking: the map's chip adds *N SOS elsewhere* while one is open outside the barangay, and opening an SOS from the banner shows all of Makati), the traffic layer, and foot traffic and Forecast (their districts are not barangays). Limits: the barangay is worked out in the browser from each pin, not stored on the ticket (the server's `district_id` is the district, 1 or 2), so the API itself cannot yet list one barangay's tickets; the Barangays menu's own counts stay city-wide so the barangays can still be compared.

## The phone's map controls

| Control | Where | What it does |
|---|---|---|
| **Tickets button** (ticket icon, red dot when a ticket has news) | Top left | Opens [My tickets](#my-tickets-the-phones-tickets-button). Stays on the screen during a trip. |
| **Compass chip** | Top right | The arrow keeps pointing at north and the letters name the way the top of the map faces. **Tap it** and the camera follows where the phone is facing: the map turns with the user, and the chip turns navy. Tap again, or pan or turn the map, and it lets go and the map goes back north-up. It is the same follow a trip starts with, available any time, and it needs a location fix inside Makati (otherwise a message says it is waiting). |
| **Map menu** (burger) | Bottom left, above the search; beside the tickets button on a trip | **Map type**: *Auto* (flat, tilts into 3D while a trip is under way), *2D map* or *3D map* (tilted, with extruded buildings), and the **Traffic flow** switch. The compass does not change the tilt; this menu does. |
| **Locate button** | Above the search | Puts the camera on the user. |
| **Report** | Bottom right, above the search | Opens the camera for a photo report, or hold it for an SOS. |

Changing the tilt while the camera is following the user keeps the zoom the person chose. Not run on a physical phone: the compass follow and the tilt are covered by widget tests and the analyzer, and the camera behaviour needs a device test.

## Commute routes are estimated

`GET /route/commute` offers up to three options: walk to a nearby hub, ride to another hub that serves the same mode, walk to the destination. The walks are real street routes from OpenRouteService (an estimate stands in if it fails). The ride is only partly real. The study has the routes but no stop order, route lines, timetables or fares, and its map pictures are not georeferenced and draw every route of a mode in one colour. So the app offers a jeepney ride only between the two end points of a route the study lists (`server/data/transit/route_ends.json` says, by hand-matched name, which hub each end is; today that is 5 jeepney routes), a train ride between two stations of one line, and a city bus ride between any two of the study's city bus stops (treated as one fixed bus network, because the study does not say which stop is on which route). UV Express and P2P routes run from Makati to places outside it, so they never serve a trip inside Makati. The line is the street path a car would take between the two stops (OpenRouteService; the straight line is kept if it fails, and trains are always a straight line), and the time is an assumed wait plus that distance at an assumed speed per mode (`server/data/transit/ride_modes.json`, our judgement, not from a source). The walking legs use the walking mode picked in the first step (Accessible uses OpenRouteService's wheelchair profile, Walkable steers around hazard reports). Arrival time counts from the moment the list is shown. The app says "Ride times are estimates."

**Known limits.** One ride per trip, no transfers. Jeepney rides exist only where both ends of a study route could be matched to a hub, so most of the 56 routes (any with an end outside our hub list, or with no named end) offer no ride yet: add them to `route_ends.json` as hubs are added. No fares, no schedules, no live positions. Tests: `server/tests/test_commute.py`, `server/tests/test_commute_route.py`, `mobile/test/commute_list_test.dart`.

## The trip: walk first, then commute, then Start

1. **Walk.** After a destination is picked the card compares the three walking routes (time, distance, hazards). The one picked decides how the commute's walking legs are routed. Not commuting? **Start walking** here walks the picked route all the way.
2. **Commute.** **Next: trip options** lists up to three walk-ride-walk options, quickest marked. Pick one, or go back to change the walking mode. If no ride is found, **Start walking** takes the picked walking route alone.
3. **Start.** The card becomes a navigation bar: the next turn with its distance ("In 120 m", from the router's turn-by-turn steps), the street the user is on, the distance and time left, the arrival time, the leg after it, and **End trip**. Where a leg has no turns (a ride, or a walk the router sent none for) it shows the leg and what is left of it. Each GPS fix moves the user along the legs, and the map draws only what is left of the trip, from the user's spot on the path. A leg is done within 25 m of its end, and within 25 m of the end of the last leg the bar says **You've arrived**. On a walk, three good GPS fixes in a row more than 30 m off the path make the app ask the server for a new walk from where the user is to the end of that leg (same mode, hazards still steered around; at most once every 15 s). While it waits the bar says it is finding a new way, and if the ask fails the old line stays and it tries again.
4. **Live view.** On a trip the camera follows the user and turns with the phone's heading, and the screen stays awake from Start until arrival or End (`wakelock_plus`). Off a trip the map stays north-up and only the pin, a blue arrow whose tip is the front (`mobile/assets/arrow.png`, the Mapbox location puck, which reads the phone's sensors), turns. The compass chip (top right) shows the arrow to north and the direction at the top of the map; it is a display, not a button. Dragging or rotating the map lets go of it, and the locate button takes it back.

**Known limits.** Foreground only: with the app closed or the phone locked tracking stops (no background location service). Only the leg being walked is re-planned (never a ride, and the commute option is not re-chosen). No voice guidance, and turn text is the router's English. A road ride follows a car's route between its stops, not the PUV's real one, and a train ride is a straight line, so on a ride the bar tracks progress along that line. **Not run on a physical phone**: the progress maths, the bar and the compass chip are unit and widget tested, but the camera follow, the heading rotation and the screen-on behaviour need a device or emulator test (Extended controls: Location routes and Virtual sensors). Tests: `mobile/test/trip_progress_test.dart`, `mobile/test/trip_state_test.dart`, `mobile/test/nav_bar_test.dart`, `mobile/test/compass_chip_test.dart`.

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

**If reports stop reaching the server.** Reports live in `reports.json` inside the server's storage folder (`STORAGE_DIR` in `server/.env`; `server/storage/` here, `db/` by default, both git-ignored). A file in there that is not a list (hand-edited, or cut off by a crash) used to make every `POST /reports` fail with a 500. The server now sets such a file aside as `reports.json.bad` and starts a new empty list, so reports go on; look in `.bad` if you need what was in it. Tickets are kept separately in `lakad.db` and are not touched. Test: `server/tests/test_store_corrupt.py`.

## Technology, AI and API disclosure

| Part | Used | Disclose as |
|---|---|---|
| Mobile | Flutter, mapbox_maps_flutter, http, camera, geolocator, sensors_plus, shared_preferences, wakelock_plus (keeps the screen on during a trip) | Open source. Mapbox free tier |
| Dashboard | React, Vite, TypeScript, mapbox-gl | Open source. Mapbox free tier |
| Server | FastAPI, JSON file store | Open source |
| Traffic | TomTom Traffic flow tiles | Third-party API, free-tier key |
| Search and routing | OpenRouteService, called by our server | Third-party API, free-tier key. Search text and an optional nearby point go to it through the server |
| Map data | OpenStreetMap, incl. an Overpass snapshot of MRT-3 and LRT-1 stations (`server/data/transit/stations.geojson`) and the 23 barangay boundaries (`models/tickets/resources/districts.json`, drawn by the dashboard's Barangays menu) | Open data (ODbL). Credit OSM |
| Transit routes and terminals | "PUV Routes in Makati" study (Ayala Land; SYSTRA Philippines, Makati BRT Study, 2025), from the hackathon's Makati Data Hub | Organizer-provided, hackathon use only. Route names and terminals only; positions were looked up by name through OpenRouteService and checked by hand. Commute options use only the hub positions and modes from it, with our own assumed ride speeds |
| Foot-traffic estimate and forecast | Our own rules, mode weights and hourly curves, plus a seasonal forecast, in plain Python. No machine-learning model and no scraped data. Inputs: the organizer's transit files and our curated district list | Predicted from assumptions and research, not measured. See "Foot traffic is predicted, not measured" |
| Ticketing rules | `models/tickets/`: hand-written rules and word lists in plain Python. Places that draw foot traffic: 719 OpenStreetMap places (`models/tickets/resources/places.json`) | Open data (ODbL). Credit OSM. No machine-learning model ships; the evaluation fits some for comparison only |
| Evaluation data | City of Chicago 311 service requests (potholes, street lights, sidewalks, water), downloaded to test the matcher; only summary numbers and plots are committed. 1,900 notes (training and gold) and 240 ticket pairs with five raters' judgments, all written by AI agents | Chicago: open data, evaluation only. The notes and judgments are AI-generated stand-ins for real data, labelled as such in `models/tickets/EVALUATION.md` |
| Evaluation tools | numpy, scipy, scikit-learn, matplotlib, pytest, in `models/.venv` | Open source. Not needed to run the server or the apps |
| AI coding assistant | Claude (Anthropic), through Claude Code: scaffolding, code, tests, docs, the ticketing rules and their evaluation, and the AI-written evaluation data above | Add every assistant anyone on the team uses |

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
