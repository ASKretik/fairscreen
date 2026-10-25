import type { ButtonHTMLAttributes, ReactNode } from "react";
import { publicUrl } from "../lib/env";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-indigo-300",
  secondary: "bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:text-slate-400",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900 disabled:text-slate-300",
  danger: "bg-white text-rose-700 ring-1 ring-inset ring-rose-200 hover:bg-rose-50 disabled:text-rose-300",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  loading = false,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; loading?: boolean }) {
  const sizing = size === "sm" ? "px-3 py-1.5 text-sm" : "px-4 py-2 text-sm";
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 ${sizing} ${VARIANTS[variant]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Spinner className="size-4" />}
      {children}
    </button>
  );
}

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>{children}</div>;
}

export function Spinner({ className = "size-5" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="4" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

export function PageSpinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-24 text-slate-500">
      <Spinner /> {label}
    </div>
  );
}

export function Alert({ tone = "error", children }: { tone?: "error" | "info" | "warning"; children: ReactNode }) {
  const tones = {
    error: "border-rose-200 bg-rose-50 text-rose-800",
    info: "border-indigo-200 bg-indigo-50 text-indigo-900",
    warning: "border-amber-200 bg-amber-50 text-amber-900",
  };
  return <div className={`rounded-lg border px-4 py-3 text-sm ${tones[tone]}`}>{children}</div>;
}

export function Logo() {
  return (
    <span className="flex items-center gap-2 font-semibold tracking-tight text-slate-900">
      <img src={publicUrl("favicon.svg")} alt="" className="size-7" />
      FairScreen
    </span>
  );
}
