// Analyst sign-in. Supabase does two things for the dashboard: Auth (sign in, sign out, keeping the session fresh)
// and reading the signed-in person's own role row in public.analysts (supabase/migrations/*_district_roles.sql;
// RLS returns only that row). The tickets come from the Lakad server (client.ts), which checks the same row.
// The client is made on first use, so with sign-in off (config/env.ts) nothing here runs.
import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";
import { ENV } from "../config/env.ts";

let client: SupabaseClient | undefined;

function supabase(): SupabaseClient {
  if (!ENV.supabaseOn) throw new Error("Sign-in is off: set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY.");
  // The session stays in this browser and is refreshed before it expires (the supabase-js defaults, spelled out).
  client ??= createClient(ENV.supabaseUrl, ENV.supabasePublishableKey, {
    auth: { persistSession: true, autoRefreshToken: true },
  });
  return client;
}

export async function signIn(email: string, password: string) {
  const { error } = await supabase().auth.signInWithPassword({ email, password });
  if (error) throw new Error(error.message);
}

// Ends this browser's session. supabase-js drops it here even when Supabase can't be reached.
export async function signOut() {
  const { error } = await supabase().auth.signOut({ scope: "local" });
  if (error) throw new Error(error.message);
}

// Calls back with the stored session once it is read, then on every change (sign in, sign out, refresh).
// Returns the unsubscribe.
export function onSession(cb: (session: Session | null) => void) {
  const { data } = supabase().auth.onAuthStateChange((_event, session) => cb(session));
  return () => data.subscription.unsubscribe();
}

// The bearer for the Lakad server, refreshed first if it has expired. null when signed out.
export async function accessToken() {
  const { data, error } = await supabase().auth.getSession();
  if (error) throw new Error(error.message);
  return data.session?.access_token ?? null;
}

// The signed-in person's role: one district, or citywide (both districts) with no district_id.
export type Role = {
  district_id: number | null;
  citywide: boolean;
  name: string;
  districts: { name: string } | null; // the district's row, joined
};

export async function getRole(userId: string): Promise<Role | null> {
  const { data, error } = await supabase()
    .from("analysts")
    .select("district_id, citywide, name, districts(name)")
    .eq("user_id", userId)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return data as Role | null;
}

// What the bar says: "District 1 (Western Makati)", "District 2 (Eastern Makati)" or "All districts".
// null: signed in, but no district yet (no row).
export function roleLabel(role: Role | null): string | null {
  if (!role) return null;
  if (role.citywide) return "All districts";
  return role.districts?.name ?? (role.district_id ? `District ${role.district_id}` : null);
}

// The Lakad server's answer to each tickets call (client.ts), for the sign-in gate: 401 the session is over,
// 403 no district, 503 the server cannot check sign-ins, 200 fine, 0 not reached.
type Listener = (status: number, detail: string) => void;
const listeners = new Set<Listener>();

export function onServerAnswer(cb: Listener) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function serverAnswered(status: number, detail = "") {
  for (const cb of listeners) cb(status, detail);
}
