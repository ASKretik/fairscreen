import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  // "/" for Firebase Hosting and local dev; "/<repo>/" for GitHub Pages (set by the deploy workflow).
  base: process.env.VITE_BASE || "/",
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
});
