// Response shapes of the Lakad API. Mirrors server/app/db/models.py (Report, Category, Status).
export type Category =
  | "pothole"
  | "open_manhole"
  | "flooded_drain"
  | "broken_streetlight"
  | "blocked_sidewalk"
  // Accessibility barriers for persons with disability. Only the Accessible route steers around the first three;
  // a steep or broken sidewalk trips anyone, so Walkable avoids it too.
  | "missing_ramp"
  | "blocked_tactile_paving"
  | "broken_elevator"
  | "unsafe_sidewalk"
  | "other"
  | "sos"; // not picked: the phone's hold-to-record button files it (POST /sos), with a video

// "rejected": a person looked at a new ticket and judged it not real. Hidden everywhere but kept, and can be reopened.
export type Status = "open" | "verified" | "assigned" | "fixed" | "rejected";

// Who must respond to an SOS. Mirrors server/app/db/models.py SosKind.
export type SosKind = "police" | "medical" | "fire_rescue";

export type Report = {
  id: string;
  category: Category;
  severity: 1 | 2 | 3; // 1 low .. 3 urgent, from the category (server/app/services/priority.py)
  lat: number;
  lng: number;
  heading: number | null; // compass heading when the photo was taken
  note: string;
  photo_url: string; // path on the API, e.g. /photos/<id>.jpg. Empty for an SOS
  video_url?: string | null; // SOS only: path on the API, e.g. /videos/<id>.mp4
  sos_kind?: SosKind | null; // SOS only: who must respond, picked here; null until sorted
  status: Status;
  created_at: string; // ISO 8601, UTC
  updated_at: string;
  // GET /tickets only (analysts signed in): the ticket engine's rank (models/tickets) and where the ticket is.
  priority?: number; // 0..100
  band?: "Critical" | "High" | "Medium" | "Low";
  district_id?: number | null; // 1 or 2; null outside both
  reporters?: number; // reports joined into this ticket
};

// PROVISIONAL: the routing API (server/app/routers/routes.py, GET /route/walk) is not built yet, so this is the
// shape the dashboard's route analytics will expect. Agree it with the server, then mirror it in the Python model.
export type RouteMode = "fastest" | "walkable" | "accessible";

export type RouteEvent = {
  id: string;
  created_at: string; // ISO 8601, UTC
  mode: RouteMode;
  length_m: number; // the route served
  fastest_length_m: number; // the Fastest route for the same trip, to measure the detour
  no_sidewalk_m_avoided: number; // meters of road without a sidewalk this route avoids
  hazard_ids_avoided: string[]; // Report ids near the Fastest route that this route steers around
};

// GET /footfall (server/app/routers/footfall.py): modeled foot traffic, a relative 0-100 index, not a count.
export type Day = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

export type FootfallScore = { index: number; lower: number; upper: number };

export type FootfallPoint = FootfallScore & {
  id: string;
  name: string;
  kind: "hub" | "anchor"; // anchor: a district's draw the transit data cannot see
  lat: number;
  lng: number;
  error_m: number;
  profile: string;
  district: string | null;
};

export type FootfallDistrict = FootfallScore & {
  id: string;
  name: string;
  lat: number;
  lng: number;
  radius_m: number;
  profile: string;
  tier: 1 | 2 | 3;
  share: number; // demand against the strongest district, any hour
  hubs: number;
  route_ends: number;
  anchor: number;
  basis: string;
};

export type Footfall = {
  kind: "estimate" | "measured";
  method: string;
  day: Day;
  hour: number;
  points: FootfallPoint[];
  districts: FootfallDistrict[];
};

// GET /footfall/series (server/app/services/forecast.py): hourly index for a zone, history then forecast.
// The history is SIMULATED until cameras exist (history_source says which); the forecast is a seasonal model.
export type SeriesPoint = {
  t: string; // ISO 8601, Manila time (+08:00), on the hour
  index: number;
  kind: "history" | "forecast";
  lower?: number | null; // 80% band, forecast only
  upper?: number | null;
};

export type Series = {
  zone: string; // "all" or a district id
  name: string;
  method: string;
  history_source: "simulated" | "measured";
  now: string;
  backtest_smape_pct: number; // error of forecasting the last simulated week from the three before it
  points: SeriesPoint[];
};
