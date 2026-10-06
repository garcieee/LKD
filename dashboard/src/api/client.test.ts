// What the client asks the Lakad API for, against a stand-in for fetch.
import { test, type TestContext } from "node:test";
import assert from "node:assert/strict";
import type { Report } from "../types/api.ts";
import { listReports, patchSosKind, patchStatus } from "./client.ts";

const API = "http://localhost:8000"; // ENV.apiBaseUrl with nothing set
const report: Report = {
  id: "a",
  category: "sos",
  severity: 3,
  lat: 14.5547,
  lng: 121.0244,
  heading: null,
  note: "",
  photo_url: "",
  status: "open",
  created_at: "2026-10-07T01:00:00+00:00",
  updated_at: "2026-10-07T01:00:00+00:00",
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

test("every report, SOS and rejected ones included, and a change goes to PATCH /reports/{id} as JSON", async (t) => {
  const fetch = serve(t, {
    [`GET ${API}/reports?include_sos=true&include_rejected=true`]: () => json([report]),
    [`PATCH ${API}/reports/a%2F1`]: (init) => json({ ...report, ...JSON.parse(String(init?.body)) }),
  });
  assert.deepEqual(await listReports(), [report]);
  assert.equal((await patchStatus("a/1", "verified")).status, "verified");
  assert.equal((await patchSosKind("a/1", "fire_rescue")).sos_kind, "fire_rescue");

  const sent = fetch.mock.calls.slice(1).map((c) => c.arguments[1]);
  assert.deepEqual(sent.map((init) => init?.body), [JSON.stringify({ status: "verified" }), JSON.stringify({ sos_kind: "fire_rescue" })]);
  assert.ok(sent.every((init) => new Headers(init?.headers).get("Content-Type") === "application/json"));
});

test("a refusal keeps the server's message, and an unreachable server says so", async (t) => {
  serve(t, {
    [`PATCH ${API}/reports/b`]: () => json({ detail: "Only an SOS has a kind." }, 422),
    [`PATCH ${API}/reports/gone`]: () => json({ detail: "No such report." }, 404),
  });
  await assert.rejects(patchSosKind("b", "police"), { status: 422, message: "Only an SOS has a kind." });
  await assert.rejects(patchStatus("gone", "fixed"), { status: 404, message: "No such report." });
  t.mock.method(globalThis, "fetch", async () => {
    throw new TypeError("fetch failed");
  });
  await assert.rejects(listReports(), { message: "API offline" });
});
