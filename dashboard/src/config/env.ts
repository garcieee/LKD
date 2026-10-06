// Reads the VITE_* variables from .env.local (copy .env.example first).
// Vite only exposes variables that start with VITE_. Under `node --test` there is no import.meta.env: all unset.
const env = import.meta.env ?? ({} as ImportMetaEnv);
const supabaseUrl = (env.VITE_SUPABASE_URL as string | undefined) ?? "";
const supabasePublishableKey = (env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined) ?? "";

export const ENV = {
  mapboxToken: env.VITE_MAPBOX_TOKEN as string,
  tomtomKey: env.VITE_TOMTOM_API_KEY as string,
  apiBaseUrl:
    (env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000",
  // Analyst sign-in (Supabase Auth). On only when both are set: then the dashboard asks for a sign-in and reads
  // /tickets with it. Off, it reads the public /reports as before.
  supabaseUrl,
  supabasePublishableKey,
  supabaseOn: Boolean(supabaseUrl && supabasePublishableKey),
} as const;
