import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { apiConfigured } from "./env";

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

/** False when frontend/.env is missing; the landing page and /demo still work. */
export const firebaseConfigured = Boolean(config.apiKey && config.projectId);

export const app = firebaseConfigured ? initializeApp(config) : null;
export const auth = app ? getAuth(app) : null;

/** Sign-in and recruiter workspaces need both Firebase and the screening API; otherwise the site runs demo-only. */
export const workspaceEnabled = firebaseConfigured && apiConfigured;
