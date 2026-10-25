import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router";
import { AuthProvider } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { ROUTER_BASENAME } from "./lib/env";
import { ServerStatusProvider } from "./lib/serverStatus";
import { PageSpinner } from "./components/ui";
import { Demo } from "./pages/Demo";
import { Landing } from "./pages/Landing";

// Signed-in pages (and the Firestore SDK they use) load on demand.
const Jobs = lazy(() => import("./pages/Jobs").then((m) => ({ default: m.Jobs })));
const NewJob = lazy(() => import("./pages/NewJob").then((m) => ({ default: m.NewJob })));
const JobPage = lazy(() => import("./pages/JobPage").then((m) => ({ default: m.JobPage })));

function Private({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <Suspense fallback={<PageSpinner />}>{children}</Suspense>
    </RequireAuth>
  );
}

function NotFound() {
  return (
    <div className="py-16 text-center">
      <p className="font-medium text-slate-900">Page not found</p>
      <Link to="/" className="mt-2 inline-block text-sm text-indigo-600">
        Go home
      </Link>
    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <ServerStatusProvider>
        <BrowserRouter basename={ROUTER_BASENAME}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Landing />} />
              <Route path="demo" element={<Demo />} />
              <Route path="jobs" element={<Private><Jobs /></Private>} />
              <Route path="jobs/new" element={<Private><NewJob /></Private>} />
              <Route path="jobs/:jobId" element={<Private><JobPage /></Private>} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ServerStatusProvider>
    </AuthProvider>
  );
}
