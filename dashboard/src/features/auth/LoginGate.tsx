// Analyst sign-in in front of the dashboard. Sign-in off (config/env.ts): the dashboard shows as before. On: a
// sign-in form, then the dashboard under a bar naming the analyst's districts, or a short message for an account
// with no district. Signed out, the dashboard is unmounted, so no ticket stays on screen.
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { ENV } from "../../config/env";
import { getRole, onServerAnswer, onSession, roleLabel, signIn, signOut } from "../../api/supabase";
import "./auth.css";

export default function LoginGate({ children }: { children: ReactNode }) {
  return ENV.supabaseOn ? <Gate>{children}</Gate> : children;
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

function Gate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(); // undefined until supabase-js has read its storage
  const [role, setRole] = useState<{ user: string; label: string | null }>(); // label null: no district
  const [note, setNote] = useState(""); // what went wrong, on whichever screen is up
  const [busy, setBusy] = useState(false);
  const user = session?.user.id;

  useEffect(() => onSession(setSession), []);

  // The role row, once per person (not again on every token refresh).
  useEffect(() => {
    if (!user) return;
    let alive = true;
    getRole(user).then(
      (row) => alive && setRole({ user, label: roleLabel(row) }),
      (e) => alive && setNote(`Could not read your district: ${message(e)}`),
    );
    return () => {
      alive = false;
    };
  }, [user]);

  // What the Lakad server answers when the dashboard asks for tickets (api/client.ts).
  useEffect(
    () =>
      onServerAnswer((status, detail) => {
        if (status === 401) {
          setNote("Your session has ended. Sign in again.");
          signOut().catch(() => {}); // supabase-js drops the session here either way
        } else if (status === 403) setRole((r) => r && { ...r, label: null });
        else if (status === 503) setNote(`The Lakad server cannot check sign-ins right now: ${detail}`);
        else if (status === 200) setNote("");
      }),
    [],
  );

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setNote("");
    try {
      await signIn(String(form.get("email")), String(form.get("password")));
    } catch (err) {
      setNote(message(err));
    }
    setBusy(false);
  }

  const out = () => signOut().catch((e) => setNote(message(e)));
  const error = (
    <p className="error" role="alert">
      {note}
    </p>
  );

  if (session === undefined)
    return (
      <Card>
        <p role="status">Checking sign-in…</p>
      </Card>
    );

  if (!session)
    return (
      <Card>
        <form className="gate-form" onSubmit={submit} aria-labelledby="gate-title">
          <h1 id="gate-title" className="panel-title">
            Analyst sign-in
          </h1>
          <label>
            Email
            <input name="email" type="email" autoComplete="username" required />
          </label>
          <label>
            Password
            <input name="password" type="password" autoComplete="current-password" required />
          </label>
          {error}
          <button className="btn confirm" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <p className="muted">Accounts are made by an admin.</p>
        </form>
      </Card>
    );

  const email = session.user.email ?? "";
  const loaded = role?.user === session.user.id;
  if (!loaded || !role.label)
    return (
      <Card>
        {loaded ? (
          <p>This account has no district yet. Ask an admin to add it.</p>
        ) : (
          !note && <p role="status">Loading your district…</p>
        )}
        {error}
        <p className="muted">Signed in as {email}</p>
        <button className="btn" onClick={out}>
          Sign out
        </button>
      </Card>
    );

  return (
    <div className="gate">
      <div className="gate-bar">
        <b>{role.label}</b>
        <span className="muted">{email}</span>
        <button className="btn" onClick={out}>
          Sign out
        </button>
        {error}
      </div>
      {children}
    </div>
  );
}

// The console's brand over a panel, in the middle of the page.
function Card({ children }: { children: ReactNode }) {
  return (
    <main className="gate-page">
      <div className="panel gate-card">
        <div className="brand">
          <b>Lakad</b>
          <small>MAKATI · LGU OPS</small>
        </div>
        {children}
      </div>
    </main>
  );
}
