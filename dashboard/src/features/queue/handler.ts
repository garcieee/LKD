// The logic of assigning a handler, with no React so `node --test` runs it (handler.test.ts).
// A ticket's path after Confirm: Verified, then a handler is picked (Assigned), then someone says it is resolved (Fixed).
import type { Report } from "../../types/api.ts";
import { HANDLERS } from "../../config/handlers.ts";

// The dropdown's value for "Someone else…", which shows a box to type a name in.
export const OTHER = "__other__";

export type Stage = "assign" | "assigned" | "resolved" | null;

// Which card the ticket shows: pick a handler, the picked one (with the resolved prompt), the resolved banner, or none
// (a new or rejected ticket is the review card's, not this one's). An assigned ticket with no name, which an older
// stepper click could leave, asks for one.
export function stageOf(r: Report): Stage {
  if (r.status === "verified") return "assign";
  if (r.status === "assigned") return r.handler ? "assigned" : "assign";
  if (r.status === "fixed") return "resolved";
  return null;
}

// The name to save from the dropdown's value and the typed box.
export function nameOf(choice: string, typed: string): string {
  return (choice === OTHER ? typed : choice).trim();
}

// The dropdown and box when the form opens on a ticket that may already have a handler: a rostered name is selected,
// any other is typed, and none starts empty.
export function startingChoice(handler: string | null | undefined): { choice: string; typed: string } {
  if (!handler) return { choice: "", typed: "" };
  return (HANDLERS as readonly string[]).includes(handler) ? { choice: handler, typed: "" } : { choice: OTHER, typed: handler };
}
