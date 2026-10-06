// Typed client for server/ (FastAPI). Base URL from VITE_API_BASE_URL (config/env.ts).
import { ENV } from "../config/env";
import type { Report, Status } from "../types/api";

const BASE = ENV.apiBaseUrl.replace(/\/+$/, "");

// Report.photo_url is a path on the API, e.g. /photos/<id>.jpg.
export const photoUrl = (path: string) => BASE + path;

// Newest first.
export async function listReports(): Promise<Report[]> {
  const body = await call<unknown>("/reports");
  if (!Array.isArray(body)) throw new Error("Unexpected /reports response");
  return body as Report[];
}

export const patchStatus = (id: string, status: Status) =>
  call<Report>(`/reports/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });

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
