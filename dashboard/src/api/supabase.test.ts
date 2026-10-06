import { test, type TestContext } from "node:test";
import assert from "node:assert/strict";
import type { Report } from "../types/api.ts";
import { ENV } from "../config/env.ts";
import { listReports, patchSosKind, patchStatus } from "./client.ts";
import { onServerAnswer, roleLabel, signIn, signOut, type Role } from "./supabase.ts";

const API = "http://localhost:8000"; // ENV.apiBaseUrl with nothing set
const SUPABASE = "https://project.example.com";
const report: Report = {
  id: "a",
  category: "pothole",
  severity: 2,
  lat: 14.5547,
  lng: 121.0244,
  heading: null,
  note: "",
  photo_url: "/photos/a.jpg",
  status: "open",
  created_at: "2026-10-07T01:00:00+00:00",
  updated_at: "2026-10-07T01:00:00+00:00",
};
const ticket: Report = { ...report, priority: 72.5, band: "Critical", district_id: 1, reporters: 3 };
// What Supabase Auth answers to a good email and password.
const SESSION = {
  access_token: "token-1",
  refresh_token: "refresh-1",
  token_type: "bearer",
  expires_in: 3600,
  user: { id: "user-1", aud: "authenticated", email: "district1@example.com", app_metadata: {}, user_metadata: {} },
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

// Stands in for the network: "METHOD url" -> reply. Anything else fails the test. Restored after it.
function serve(t: TestContext, routes: Record<string, (init?: RequestInit) => Response>) {
  return t.mock.method(globalThis, "fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${input instanceof Request ? input.url : String(input)}`;
    const reply = routes[key];
    if (!reply) throw new TypeError(`unexpected fetch: ${key}`);
    return reply(init);
  });
}

// Sign-in on for one test, pointed at a project that only `serve` answers for.
function signInOn(t: TestContext) {
  Object.assign(ENV, { supabaseUrl: SUPABASE, supabasePublishableKey: "sb_publishable_test", supabaseOn: true });
  t.after(() => Object.assign(ENV, { supabaseUrl: "", supabasePublishableKey: "", supabaseOn: false }));
}

const role = (over: Partial<Role>): Role => ({ district_id: null, citywide: false, name: "", districts: null, ...over });

test("roleLabel: each district by name, citywide as all districts", () => {
  assert.equal(
    roleLabel(role({ district_id: 1, districts: { name: "District 1 (Western Makati)" } })),
    "District 1 (Western Makati)",
  );
  assert.equal(
    roleLabel(role({ district_id: 2, districts: { name: "District 2 (Eastern Makati)" } })),
    "District 2 (Eastern Makati)",
  );
  assert.equal(roleLabel(role({ citywide: true })), "All districts");
});

test("roleLabel: no row means no district yet; a district whose name did not come back still counts", () => {
  assert.equal(roleLabel(null), null);
  assert.equal(roleLabel(role({})), null, "neither a district nor citywide");
  assert.equal(roleLabel(role({ district_id: 2 })), "District 2");
});

test("sign-in off: the public /reports as before, no token, and no Supabase client", async (t) => {
  assert.equal(ENV.supabaseOn, false, "no VITE_ variables under node --test");
  const fetch = serve(t, {
    [`GET ${API}/reports?include_sos=true&include_rejected=true`]: () => json([report]),
    [`PATCH ${API}/reports/a`]: (init) => json({ ...report, ...JSON.parse(String(init?.body)) }),
  });
  assert.deepEqual(await listReports(), [report]);
  assert.equal((await patchStatus("a", "fixed")).status, "fixed");
  assert.ok(fetch.mock.calls.every((c) => !new Headers(c.arguments[1]?.headers).has("Authorization")));
  await assert.rejects(signIn("district1@example.com", "pw"), /Sign-in is off/);
  assert.equal(fetch.mock.calls.length, 2, "nothing went to Supabase");
});

test("sign-in on: GET /tickets and PATCH /tickets/{id} carry the analyst's access token", async (t) => {
  signInOn(t);
  const fetch = serve(t, {
    [`POST ${SUPABASE}/auth/v1/token?grant_type=password`]: () => json(SESSION),
    [`GET ${API}/tickets`]: () => json([ticket]),
    [`PATCH ${API}/tickets/a%2F1`]: (init) => json({ ...ticket, ...JSON.parse(String(init?.body)) }),
    [`POST ${SUPABASE}/auth/v1/logout?scope=local`]: () => new Response(null, { status: 204 }),
  });
  await signIn("district1@example.com", "pw");
  assert.deepEqual(await listReports(), [ticket]);
  const saved = await patchStatus("a/1", "verified");
  assert.equal(saved.status, "verified");
  assert.equal(saved.district_id, 1);

  const lakad = fetch.mock.calls.filter((c) => String(c.arguments[0]).startsWith(API)).map((c) => c.arguments[1]);
  assert.deepEqual(
    lakad.map((init) => new Headers(init?.headers).get("Authorization")),
    ["Bearer token-1", "Bearer token-1"],
  );
  assert.equal(lakad[1]?.body, JSON.stringify({ status: "verified" }));
  assert.equal(new Headers(lakad[1]?.headers).get("Content-Type"), "application/json");

  // Signed out: nothing goes to the server, and the gate hears 401 (back to the sign-in form).
  await signOut();
  const answers: number[] = [];
  t.after(onServerAnswer((status) => answers.push(status)));
  const before = fetch.mock.calls.length;
  await assert.rejects(listReports(), /Signed out/);
  assert.deepEqual(answers, [401]);
  assert.equal(fetch.mock.calls.length, before);
});

test("sign-in on: the server's 401, 403 and 503 reach the gate; a 404 keeps the server's message", async (t) => {
  signInOn(t);
  const replies = [
    json({ detail: "Sign in again." }, 401),
    json({ detail: "No district for this account." }, 403),
    json({ detail: "Supabase is unreachable." }, 503),
    json([ticket]),
  ];
  serve(t, {
    [`POST ${SUPABASE}/auth/v1/token?grant_type=password`]: () => json(SESSION),
    [`GET ${API}/tickets`]: () => replies.shift()!,
    [`PATCH ${API}/tickets/gone`]: () => json({ detail: "No such ticket." }, 404),
  });
  await signIn("district1@example.com", "pw");
  const answers: [number, string][] = [];
  t.after(onServerAnswer((status, detail) => answers.push([status, detail])));

  await assert.rejects(listReports(), { status: 401, message: "Sign in again." });
  await assert.rejects(listReports(), { status: 403 });
  await assert.rejects(listReports(), { status: 503 });
  assert.deepEqual(await listReports(), [ticket]);
  await assert.rejects(patchStatus("gone", "fixed"), { status: 404, message: "No such ticket." });
  assert.deepEqual(answers, [
    [401, "Sign in again."],
    [403, "No district for this account."],
    [503, "Supabase is unreachable."],
    [200, ""],
    [404, "No such ticket."],
  ]);
});

test("sign-in on: who must respond to an SOS goes to PATCH /tickets/{id} as {sos_kind}, with the token", async (t) => {
  signInOn(t);
  const fetch = serve(t, {
    [`POST ${SUPABASE}/auth/v1/token?grant_type=password`]: () => json(SESSION),
    [`PATCH ${API}/tickets/a`]: (init) => json({ ...ticket, category: "sos", ...JSON.parse(String(init?.body)) }),
  });
  await signIn("district1@example.com", "pw");
  assert.equal((await patchSosKind("a", "fire_rescue")).sos_kind, "fire_rescue");

  const [init] = fetch.mock.calls.filter((c) => String(c.arguments[0]).startsWith(API)).map((c) => c.arguments[1]);
  assert.equal(init?.body, JSON.stringify({ sos_kind: "fire_rescue" }));
  assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer token-1");
});
