import { coverage, primaryEducation, topGap, topMatches, truncate } from "../lib/candidates";
import type { Candidate, JobRequirements } from "../types";
import { ScoreBar } from "./ScoreBar";
import { StatusChip } from "./StatusChip";

interface Props {
  rows: Candidate[];
  ranks: Map<string, number>;
  requirements: JobRequirements;
  sortDir: "desc" | "asc";
  onSort(): void;
  onOpen(c: Candidate): void;
  selectedId: string | null;
}

/** The blind ranked table. It never renders identity or file names, revealed or not. */
export function CandidateTable({ rows, ranks, requirements, sortDir, onSort, onOpen, selectedId }: Props) {
  if (rows.length === 0) {
    return <p className="px-6 py-12 text-center text-sm text-slate-500">No candidates here yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium tracking-wide text-slate-500 uppercase">
          <tr>
            <th className="px-4 py-3">#</th>
            <th className="px-4 py-3">Candidate</th>
            <th className="px-4 py-3">
              <button type="button" onClick={onSort} className="inline-flex items-center gap-1 uppercase hover:text-slate-800">
                Score <span aria-hidden="true">{sortDir === "desc" ? "↓" : "↑"}</span>
                <span className="sr-only">{sortDir === "desc" ? "sorted high to low" : "sorted low to high"}</span>
              </button>
            </th>
            <th className="px-4 py-3">Must-haves</th>
            <th className="px-4 py-3">Matched</th>
            <th className="px-4 py-3">Top gap</th>
            <th className="px-4 py-3">Education</th>
            <th className="px-4 py-3">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((c) => {
            const selected = c.id === selectedId;
            const base = `cursor-pointer transition-colors ${selected ? "bg-indigo-50/70" : "hover:bg-slate-50"}`;
            if (!c.score || !c.evaluation) {
              return (
                <tr key={c.id} className={base} onClick={() => onOpen(c)}>
                  <td className="px-4 py-3 text-slate-400">–</td>
                  <td className="px-4 py-3 font-mono text-sm font-medium whitespace-nowrap text-slate-800">{c.anonId}</td>
                  <td className="px-4 py-3 text-slate-500" colSpan={5}>
                    {c.status === "failed" ? (
                      <span className="text-amber-800">{truncate(c.error ?? "Processing failed.", 90)}</span>
                    ) : (
                      "Parsing, anonymising and evaluating…"
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusChip status={c.status} />
                  </td>
                </tr>
              );
            }
            const cov = coverage(c.evaluation.must_have);
            const edu = primaryEducation(c);
            const gap = topGap(c);
            return (
              <tr key={c.id} className={base} onClick={() => onOpen(c)}>
                <td className="px-4 py-3 font-medium text-slate-500">{ranks.get(c.id) ?? "–"}</td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    className="font-mono text-sm font-medium whitespace-nowrap text-slate-900 hover:text-indigo-700"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpen(c);
                    }}
                  >
                    {c.anonId}
                  </button>
                  {c.revealed && <span className="ml-2 rounded bg-indigo-50 px-1.5 py-0.5 text-[11px] font-medium text-indigo-700">revealed</span>}
                </td>
                <td className="px-4 py-3">
                  <div className="flex w-36 items-center gap-2">
                    <ScoreBar value={c.score.total} label={`Score ${c.score.total.toFixed(0)} of 100`} />
                    <span className="w-8 text-right font-semibold tabular-nums">{c.score.total.toFixed(0)}</span>
                  </div>
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <span className="font-medium tabular-nums">
                    {cov.met}/{cov.total}
                  </span>
                  {cov.partial > 0 && <span className="ml-1 text-xs text-slate-500">+{cov.partial} partial</span>}
                  {c.score.missing_must_have && (
                    <span className="mt-1 block w-fit rounded-full bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-700 ring-1 ring-rose-200 ring-inset">
                      missing must-have
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex w-52 flex-col items-start gap-1">
                    {topMatches(c, requirements).map((m) => (
                      <span key={m} title={m} className="max-w-full truncate rounded-md bg-emerald-50 px-2 py-0.5 text-xs text-emerald-800">
                        {m}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="max-w-48 px-4 py-3 text-xs text-slate-600" title={gap ?? undefined}>
                  {gap ? truncate(gap, 48) : "–"}
                </td>
                <td className="max-w-56 px-4 py-3 text-xs">
                  {edu ? (
                    <>
                      <div className="truncate font-medium text-slate-800" title={edu.institution ?? undefined}>
                        {edu.institution ?? "–"}
                      </div>
                      <div className="truncate text-slate-500">
                        {[edu.degree, edu.grade].filter(Boolean).join(" · ") || "–"}
                      </div>
                    </>
                  ) : (
                    <span className="text-slate-400">–</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <StatusChip status={c.status} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
