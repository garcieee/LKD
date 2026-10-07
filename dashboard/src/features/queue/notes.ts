// Notes the person at the dashboard leaves for the reporter, with no React so `node --test` runs it (notes.test.ts).
// Rejecting needs a reason; confirming and resolving take an optional note. The reporter reads them in the phone's
// My tickets.
import type { Report } from "../../types/api.ts";

export const NOTE_MAX = 280; // the server's limit

// What is sent: the note without the spaces round it, or nothing when it is blank.
export const cleanNote = (text: string): string | undefined => text.trim() || undefined;

// Rejecting needs a reason the reporter can read: a blank box is not one.
export const canReject = (text: string) => cleanNote(text) !== undefined;

export type NoteLine = { label: string; text: string };

// The notes to show on a ticket, in the order they happened: the one left on confirming (kept for every status after),
// then the one left on resolving. The reason for a rejection is shown by the rejected banner, not here.
export function notesFor(r: Report): NoteLine[] {
  const lines: NoteLine[] = [];
  if (r.verified_note && (r.status === "verified" || r.status === "assigned" || r.status === "fixed")) {
    lines.push({ label: "Note when confirmed", text: r.verified_note });
  }
  if (r.resolved_note && r.status === "fixed") lines.push({ label: "Note when resolved", text: r.resolved_note });
  return lines;
}

// Why a rejected ticket was rejected, if it is rejected and has a reason.
export const rejectedReason = (r: Report): string | null => (r.status === "rejected" ? (r.rejected_note ?? null) : null);
