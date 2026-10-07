// Typed client for server/ (FastAPI). Base URL from VITE_API_BASE_URL (config/env.ts).
import { ENV } from "../config/env.ts"; // .ts so `node --test` can resolve it
import type { Day, Footfall, Report, Series, SosKind, Status } from "../types/api";

const BASE = ENV.apiBaseUrl.replace(/\/+$/, "");

// Report.photo_url is a path on the API, e.g. /photos/<id>.jpg. Report.video_url (an SOS) is the same kind of path.
export const photoUrl = (path: string) => BASE + path;
export const videoUrl = photoUrl;

// Newest first. The public list leaves SOS and rejected tickets out; the dashboard is where they are answered
// and where a rejected one can be reopened.
export async function listReports(): Promise<Report[]> {
  const body = await call<unknown>("/reports?include_sos=true&include_rejected=true");
  if (!Array.isArray(body)) throw new Error("Unexpected /reports response");
  return body as Report[];
}

// Modeled foot traffic at a day and hour (server defaults both to now in Manila).
export const getFootfall = (day: Day, hour: number) => call<Footfall>(`/footfall?day=${day}&hour=${hour}`);

// A week of history and three days of forecast for a zone ("all" or a district id).
export const getSeries = (zone: string) =>
  call<Series>(`/footfall/series?zone=${encodeURIComponent(zone)}&past_days=7&future_days=3`);

// A note for the reporter can go with a status: required to reject (the server refuses a rejection without one, 422),
// optional to confirm or resolve.
export const patchStatus = (id: string, status: Status, status_note?: string) => patch(id, { status, status_note });

// Assigns a handler (a name). With `status` ("assigned") the ticket moves on in the same save; without, the name of
// an assigned or resolved ticket changes. The server refuses a handler before the ticket is verified (422).
export const patchHandler = (id: string, handler: string, status?: Status) => patch(id, { handler, status });

// Who must respond to an SOS. The server refuses a kind on anything else (422).
export const patchSosKind = (id: string, sos_kind: SosKind) => patch(id, { sos_kind });

function patch(id: string, change: { status?: Status; sos_kind?: SosKind; handler?: string; status_note?: string }) {
  const init = { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(change) };
  return call<Report>(`/reports/${encodeURIComponent(id)}`, init);
}

// Throws "API offline" when the server can't be reached, else the server's own message.
async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, { ...init, signal: AbortSignal.timeout(8_000) });
  } catch {
    throw new Error("API offline");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(detail(body) ?? `HTTP ${res.status}`);
  return body as T;
}

// FastAPI errors: {"detail": "No such report."}, or a list of {msg} for a 422.
function detail(body: unknown): string | undefined {
  const d = (body as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && typeof d[0]?.msg === "string") return d[0].msg;
  return undefined;
}
