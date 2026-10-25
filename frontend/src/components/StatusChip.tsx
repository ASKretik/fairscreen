import type { CandidateStatus } from "../types";
import { Spinner } from "./ui";

const STYLES: Record<CandidateStatus, string> = {
  processing: "bg-sky-50 text-sky-700 ring-sky-200",
  scored: "bg-slate-100 text-slate-700 ring-slate-200",
  shortlisted: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  rejected: "bg-rose-50 text-rose-700 ring-rose-200",
  failed: "bg-amber-50 text-amber-800 ring-amber-200",
};

const LABELS: Record<CandidateStatus, string> = {
  processing: "Processing",
  scored: "To review",
  shortlisted: "Shortlisted",
  rejected: "Rejected",
  failed: "Failed",
};

export function StatusChip({ status }: { status: CandidateStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset ${STYLES[status]}`}
    >
      {status === "processing" && <Spinner className="size-3" />}
      {LABELS[status]}
    </span>
  );
}

export const STATUS_LABELS = LABELS;
