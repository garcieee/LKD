// Reads the VITE_* variables from .env.local (copy .env.example first).
// Vite only exposes variables that start with VITE_. Under `node --test` there is no import.meta.env: all unset.
const env = import.meta.env ?? ({} as ImportMetaEnv);

export const ENV = {
  mapboxToken: env.VITE_MAPBOX_TOKEN as string,
  tomtomKey: env.VITE_TOMTOM_API_KEY as string,
  apiBaseUrl:
    (env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000",
} as const;
