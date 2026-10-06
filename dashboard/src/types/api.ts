// Response shapes of the Lakad API. Mirrors server/app/db/models.py (Report, Category, Status).
export type Category =
  | "pothole"
  | "open_manhole"
  | "flooded_drain"
  | "broken_streetlight"
  | "blocked_sidewalk"
  | "other";

export type Status = "open" | "verified" | "assigned" | "fixed";

export type Report = {
  id: string;
  category: Category;
  severity: 1 | 2 | 3; // 1 low .. 3 urgent, from the category (server/app/services/priority.py)
  lat: number;
  lng: number;
  heading: number | null; // compass heading when the photo was taken
  note: string;
  photo_url: string; // path on the API, e.g. /photos/<id>.jpg
  status: Status;
  created_at: string; // ISO 8601, UTC
  updated_at: string;
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
