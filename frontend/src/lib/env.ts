// Build-time settings from Vite env vars, in one place (no imports, so no cycles).

export const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "");

/** False on a production build without VITE_API_URL (a demo-only deployment): no health checks, no sign-in. */
export const apiConfigured = Boolean(import.meta.env.VITE_API_URL) || import.meta.env.DEV;

/** Vite's base path ("/" or "/<repo>/" on GitHub Pages), for files in public/. */
export function publicUrl(path: string): string {
  return `${import.meta.env.BASE_URL}${path.replace(/^\/+/, "")}`;
}

/** The router basename: the base path without its trailing slash. */
export const ROUTER_BASENAME = import.meta.env.BASE_URL.replace(/\/+$/, "") || "/";

/** Public source repository, shown in the footer. */
export const REPO_URL = import.meta.env.VITE_REPO_URL || "https://github.com/ASKretik/fairscreen";
