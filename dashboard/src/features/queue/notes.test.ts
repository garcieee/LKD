import { test } from "node:test";
import assert from "node:assert/strict";
import type { Report } from "../../types/api.ts";
import { NOTE_MAX, canReject, cleanNote, notesFor, rejectedReason } from "./notes.ts";

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

test("a note is sent trimmed, and a blank one is no note", () => {
  assert.equal(cleanNote("  A crew has been told.  "), "A crew has been told.");
  assert.equal(cleanNote(""), undefined);
  assert.equal(cleanNote("   \n  "), undefined);
});

test("a ticket cannot be rejected without a reason: a blank or spaces-only note does not count", () => {
  assert.equal(canReject(""), false);
  assert.equal(canReject("    "), false);
  assert.equal(canReject("Not a hazard."), true);
  assert.equal(canReject("  x "), true);
});

test("the limit matches the server's", () => {
  assert.equal(NOTE_MAX, 280);
});

test("the notes on a ticket come in the order they happened, and only once they apply", () => {
  const all = { verified_note: "A crew has been told.", resolved_note: "Filled and sealed." };
  assert.deepEqual(notesFor(report({ ...all, status: "verified" })).map((n) => n.text), ["A crew has been told."]);
  assert.deepEqual(notesFor(report({ ...all, status: "assigned" })).map((n) => n.text), ["A crew has been told."]);
  assert.deepEqual(notesFor(report({ ...all, status: "fixed" })).map((n) => n.label), ["Note when confirmed", "Note when resolved"]);
  assert.deepEqual(notesFor(report({ ...all, status: "open" })), [], "a reopened ticket shows no old notes");
  assert.deepEqual(notesFor(report({ ...all, status: "rejected" })), [], "the reason has its own banner");
});

test("a ticket with no notes shows none", () => {
  assert.deepEqual(notesFor(report({ status: "fixed" })), []);
  assert.deepEqual(notesFor(report({ status: "verified", verified_note: null })), []);
});

test("the reason for a rejection shows only while the ticket is rejected", () => {
  assert.equal(rejectedReason(report({ status: "rejected", rejected_note: "Duplicate." })), "Duplicate.");
  assert.equal(rejectedReason(report({ status: "open", rejected_note: "Duplicate." })), null, "reopened");
  assert.equal(rejectedReason(report({ status: "rejected" })), null, "an older rejection with no reason");
});
