import type { ReactNode } from "react";
import { Link } from "react-router";
import { useAuth } from "../auth/AuthContext";
import { workspaceEnabled } from "../lib/firebase";
import { SignInButton } from "./Layout";
import { Card, PageSpinner } from "./ui";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (!workspaceEnabled) {
    return (
      <Card className="mx-auto max-w-md p-8 text-center">
        <h1 className="text-lg font-semibold text-slate-900">Recruiter workspaces are opening soon</h1>
        <p className="mt-2 text-sm text-slate-600">
          Sign-in isn't available on this site yet. The interactive demo shows the full screening flow in the meantime.
        </p>
        <Link
          to="/demo"
          className="mt-6 inline-flex rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          Try the live demo
        </Link>
        {import.meta.env.DEV && (
          <p className="mt-6 text-xs text-slate-400">
            Dev: copy <code>frontend/.env.example</code> to <code>frontend/.env</code> and fill in the Firebase settings.
          </p>
        )}
      </Card>
    );
  }
  if (loading) return <PageSpinner />;
  if (!user) {
    return (
      <Card className="mx-auto max-w-md p-8 text-center">
        <h1 className="text-lg font-semibold text-slate-900">Sign in to see your jobs</h1>
        <p className="mt-2 text-sm text-slate-600">Your jobs and screening results are saved to your Google account.</p>
        <SignInButton className="mt-6 inline-block" />
      </Card>
    );
  }
  return <>{children}</>;
}
