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
