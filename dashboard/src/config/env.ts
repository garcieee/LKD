// Reads the VITE_* variables from .env.local (copy .env.example first).
// Vite only exposes variables that start with VITE_.
export const ENV = {
  mapboxToken: import.meta.env.VITE_MAPBOX_TOKEN as string,
  tomtomKey: import.meta.env.VITE_TOMTOM_API_KEY as string,
  apiBaseUrl:
    (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000",
} as const;
