// Typed client for server/ (FastAPI). Base URL from VITE_API_BASE_URL (config/env.ts).
import { ENV } from "../config/env.ts"; // .ts so `node --test` can resolve it
import { accessToken, serverAnswered } from "./supabase.ts";
import type { Day, Footfall, Report, Series, Status } from "../types/api";

const BASE = ENV.apiBaseUrl.replace(/\/+$/, "");

// Report.photo_url is a path on the API, e.g. /photos/<id>.jpg. Report.video_url (an SOS) is the same kind of path.
export const photoUrl = (path: string) => BASE + path;
export const videoUrl = photoUrl;

// Newest first. The public list leaves SOS and rejected tickets out; the dashboard is where they are answered
// and where a rejected one can be reopened. With sign-in on: the tickets of the analyst's districts, all statuses.
export async function listReports(): Promise<Report[]> {
  const body = ENV.supabaseOn
    ? await signedIn<unknown>("/tickets")
    : await call<unknown>("/reports?include_sos=true&include_rejected=true");
  if (!Array.isArray(body)) throw new Error("Unexpected /reports response");
  return body as Report[];
}

// Modeled foot traffic at a day and hour (server defaults both to now in Manila).
export const getFootfall = (day: Day, hour: number) => call<Footfall>(`/footfall?day=${day}&hour=${hour}`);

// A week of history and three days of forecast for a zone ("all" or a district id).
export const getSeries = (zone: string) =>
  call<Series>(`/footfall/series?zone=${encodeURIComponent(zone)}&past_days=7&future_days=3`);

// With sign-in on, the change goes to the ticket (PATCH /tickets/{id}); off, to the report as before.
export const patchStatus = (id: string, status: Status) => {
  const init = { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) };
  return ENV.supabaseOn
    ? signedIn<Report>(`/tickets/${encodeURIComponent(id)}`, init)
    : call<Report>(`/reports/${encodeURIComponent(id)}`, init);
};

// Throws "API offline" when the server can't be reached, else the server's own message.
async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, { ...init, signal: AbortSignal.timeout(8_000) });
  } catch {
    throw new Error("API offline");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw Object.assign(new Error(detail(body) ?? `HTTP ${res.status}`), { status: res.status });
  return body as T;
}

// Sign-in on: the analyst's Supabase access token goes with the call. Every answer also goes to the sign-in gate
// (serverAnswered): 401 sends the person back to sign in, 403 shows "no district", 503 says sign-in is down.
async function signedIn<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await accessToken();
  if (!token) {
    serverAnswered(401);
    throw new Error("Signed out");
  }
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  try {
    const body = await call<T>(path, { ...init, headers });
    serverAnswered(200);
    return body;
  } catch (e) {
    serverAnswered((e as { status?: number }).status ?? 0, (e as Error).message);
    throw e;
  }
}

// FastAPI errors: {"detail": "No such report."}, or a list of {msg} for a 422.
function detail(body: unknown): string | undefined {
  const d = (body as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && typeof d[0]?.msg === "string") return d[0].msg;
  return undefined;
}
