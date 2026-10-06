import { test } from "node:test";
import assert from "node:assert/strict";
import type { Report } from "../../types/api.ts";
import { HANDLERS } from "../../config/handlers.ts";
import { OTHER, nameOf, stageOf, startingChoice } from "./handler.ts";

const report = (over: Partial<Report> = {}): Report => ({
  id: "3f2a9c01",
  category: "pothole",
  severity: 2,
  lat: 14.5547,
  lng: 121.0244,
  heading: null,
  note: "",
  photo_url: "/photos/3f2a9c01.jpg",
  status: "open",
  created_at: "2026-10-07T00:00:00Z",
  updated_at: "2026-10-07T00:00:00Z",
  ...over,
});

test("a ticket's card follows its status: nothing for new or rejected, pick, picked, resolved", () => {
  assert.equal(stageOf(report({ status: "open" })), null, "a new ticket is the review card's");
  assert.equal(stageOf(report({ status: "rejected" })), null);
  assert.equal(stageOf(report({ status: "verified" })), "assign");
  assert.equal(stageOf(report({ status: "assigned", handler: "Ana Reyes · Public Works" })), "assigned");
  assert.equal(stageOf(report({ status: "fixed", handler: "Ana Reyes · Public Works" })), "resolved");
});

test("an assigned ticket with no name asks for one, rather than showing an empty locked field", () => {
  assert.equal(stageOf(report({ status: "assigned" })), "assign");
  assert.equal(stageOf(report({ status: "assigned", handler: null })), "assign");
  assert.equal(stageOf(report({ status: "assigned", handler: "" })), "assign");
});

test("a resolved ticket is resolved even without a name", () => {
  assert.equal(stageOf(report({ status: "fixed" })), "resolved");
});

test("nameOf takes the dropdown's name, or the typed one for Someone else, trimmed", () => {
  assert.equal(nameOf(HANDLERS[0], "ignored"), HANDLERS[0]);
  assert.equal(nameOf(OTHER, "  Carlo Dela Cruz "), "Carlo Dela Cruz");
  assert.equal(nameOf(OTHER, "   "), "", "nothing typed is nothing to save");
  assert.equal(nameOf("", "typed but not chosen"), "", "nothing chosen yet");
});

test("the change form opens on the current name: rostered ones selected, others typed, none empty", () => {
  assert.deepEqual(startingChoice(null), { choice: "", typed: "" });
  assert.deepEqual(startingChoice(undefined), { choice: "", typed: "" });
  assert.deepEqual(startingChoice(HANDLERS[2]), { choice: HANDLERS[2], typed: "" });
  assert.deepEqual(startingChoice("Carlo Dela Cruz"), { choice: OTHER, typed: "Carlo Dela Cruz" });
});

test("every name on the roster fits what the server accepts (1 to 60 characters) and none repeats", () => {
  assert.ok(HANDLERS.length >= 5, "enough to demo a choice");
  for (const h of HANDLERS) assert.ok(h.length >= 1 && h.length <= 60, h);
  assert.equal(new Set(HANDLERS).size, HANDLERS.length);
  assert.ok(!(HANDLERS as readonly string[]).includes(OTHER));
});
