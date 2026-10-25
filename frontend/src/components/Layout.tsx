import { useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { useAuth } from "../auth/AuthContext";
import { REPO_URL } from "../lib/env";
import { auth, workspaceEnabled } from "../lib/firebase";
import { useServerStatus } from "../lib/serverStatus";
import { Button, Logo, Spinner } from "./ui";

/** Marketing sections on the landing page, linked from the header and footer. */
export const SECTIONS = [
  { hash: "features", label: "Product" },
  { hash: "how", label: "How it works" },
  { hash: "fairness", label: "Fairness" },
  { hash: "pricing", label: "Pricing" },
  { hash: "faq", label: "FAQ" },
] as const;

function ColdStartBanner() {
  const { status, retry } = useServerStatus();
  const { pathname } = useLocation();
  // Only the recruiter workspace needs the server; the landing page and demo never call it.
  if (!pathname.startsWith("/jobs")) return null;
  if (status === "slow") {
    return (
      <div className="flex items-center justify-center gap-2 bg-amber-50 px-4 py-2 text-sm text-amber-900">
        <Spinner className="size-4" /> Waking up the screening server (can take up to a minute)…
      </div>
    );
  }
  if (status === "down") {
    return (
      <div className="flex flex-wrap items-center justify-center gap-3 bg-rose-50 px-4 py-2 text-sm text-rose-800">
        Can't reach the screening server right now. Creating jobs and uploads won't work.
        <button type="button" onClick={retry} className="font-medium underline">
          Try again
        </button>
      </div>
    );
  }
  return null;
}

interface SignInProps {
  className?: string;
  label?: string;
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md";
  /** Where to go once signed in (stays put if the popup is closed). */
  redirectTo?: string;
  fullWidth?: boolean;
}

export function SignInButton({
  className = "",
  label = "Sign in with Google",
  variant = "primary",
  size = "md",
  redirectTo,
  fullWidth = false,
}: SignInProps) {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!workspaceEnabled) return null;
  return (
    <span className={`${fullWidth ? "block" : ""} ${className}`}>
      <Button
        variant={variant}
        size={size}
        loading={busy}
        className={fullWidth ? "w-full" : ""}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await signIn();
            if (redirectTo && auth?.currentUser) navigate(redirectTo);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {label}
      </Button>
      {error && <span className="mt-1 block text-xs text-rose-700">{error}</span>}
    </span>
  );
}

/** The main call to action: the workspace when it's available, otherwise the demo. */
export function PrimaryCta({ size = "md", className = "", fullWidth = false }: { size?: "sm" | "md"; className?: string; fullWidth?: boolean }) {
  const { user } = useAuth();
  const pad = size === "sm" ? "px-3 py-1.5" : "px-5 py-2.5";
  const linkClass = `inline-flex items-center justify-center rounded-lg bg-indigo-600 ${pad} text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 ${fullWidth ? "w-full" : ""} ${className}`;
  if (user) {
    return (
      <Link to="/jobs" className={linkClass}>
        Go to my jobs
      </Link>
    );
  }
  if (workspaceEnabled) {
    return <SignInButton label="Start screening free" size={size} redirectTo="/jobs/new" className={className} fullWidth={fullWidth} />;
  }
  return (
    <Link to="/demo" className={linkClass}>
      Try the live demo
    </Link>
  );
}

function Header() {
  const { user, signOut } = useAuth();
  const navClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-1.5 text-sm font-medium ${isActive ? "bg-slate-100 text-slate-900" : "text-slate-600 hover:text-slate-900"}`;
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
        <div className="flex items-center gap-8">
          <Link to="/" aria-label="FairScreen home">
            <Logo />
          </Link>
          {!user && (
            <nav className="hidden items-center gap-1 lg:flex" aria-label="Sections">
              {SECTIONS.map((s) => (
                <Link key={s.hash} to={{ pathname: "/", hash: s.hash }} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
                  {s.label}
                </Link>
              ))}
            </nav>
          )}
        </div>
        <nav className="flex items-center gap-1 sm:gap-2" aria-label="Main">
          {user && (
            <NavLink to="/jobs" end className={navClass}>
              My jobs
            </NavLink>
          )}
          <NavLink to="/demo" className={navClass}>
            Demo
          </NavLink>
          {user ? (
            <div className="ml-2 flex items-center gap-3">
              <span className="hidden text-sm text-slate-500 md:inline">{user.email}</span>
              <Button variant="secondary" size="sm" onClick={signOut}>
                Sign out
              </Button>
            </div>
          ) : (
            <>
              <SignInButton label="Sign in" variant="ghost" size="sm" redirectTo="/jobs" className="hidden sm:inline" />
              <PrimaryCta size="sm" className="ml-1" />
            </>
          )}
        </nav>
      </div>
    </header>
  );
}

function Footer() {
  const columns: { title: string; links: { label: string; to?: string; hash?: string; href?: string }[] }[] = [
    {
      title: "Product",
      links: [
        { label: "Live demo", to: "/demo" },
        { label: "How it works", hash: "how" },
        { label: "Features", hash: "features" },
        { label: "Pricing", hash: "pricing" },
      ],
    },
    {
      title: "Trust",
      links: [
        { label: "Blind-screening policy", hash: "fairness" },
        { label: "How scores work", hash: "scoring" },
        { label: "Privacy and data", hash: "faq" },
      ],
    },
    {
      title: "Resources",
      links: [
        { label: "Source code", href: REPO_URL },
        { label: "Evaluation results", href: `${REPO_URL}#evaluation` },
        { label: "Design decisions", href: `${REPO_URL}/blob/main/decisionsp4.md` },
      ],
    },
  ];
  const linkClass = "text-sm text-slate-600 hover:text-slate-900";
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-5">
        <div className="md:col-span-2">
          <Logo />
          <p className="mt-3 max-w-xs text-sm text-slate-500">
            Blind resume screening for small hiring teams. Judge candidates on skills and experience, not on who they are.
          </p>
        </div>
        {columns.map((col) => (
          <div key={col.title}>
            <h3 className="text-xs font-semibold tracking-wide text-slate-900 uppercase">{col.title}</h3>
            <ul className="mt-3 space-y-2">
              {col.links.map((l) => (
                <li key={l.label}>
                  {l.href ? (
                    <a href={l.href} className={linkClass} target="_blank" rel="noreferrer">
                      {l.label}
                    </a>
                  ) : (
                    <Link to={l.to ?? { pathname: "/", hash: l.hash }} className={linkClass}>
                      {l.label}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-slate-100">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-6 text-xs text-slate-400 sm:flex-row sm:justify-between sm:px-6">
          <span>© {new Date().getFullYear()} FairScreen</span>
          <span>Built on pretrained AI models through APIs. No model training, no resume storage.</span>
        </div>
      </div>
    </footer>
  );
}

export function Layout() {
  const { pathname } = useLocation();
  // The landing page lays out its own full-width sections.
  const fullBleed = pathname === "/";
  return (
    <div className="flex min-h-screen flex-col">
      <ColdStartBanner />
      <Header />
      <main className={fullBleed ? "flex-1" : "mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6"}>
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
