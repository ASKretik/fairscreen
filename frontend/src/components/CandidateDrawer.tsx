import { useEffect, useState, type ReactNode } from "react";
import { formatMonths, percent, requirementMap, tagWeight } from "../lib/candidates";
import { labelName } from "../lib/demoPool";
import type { Candidate, Decision, Job, RevealedIdentity, RequirementVerdict, WorkspaceActions } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";
import { ScoreBar } from "./ScoreBar";
import { StatusChip } from "./StatusChip";
import { Alert, Button, Spinner } from "./ui";

interface Props {
  candidate: Candidate;
  job: Job;
  actions: WorkspaceActions;
  currentUid: string | null;
  onClose(): void;
  /** Demo pool: show the resume's dataset category. */
  showLabel?: boolean;
}

const VERDICT = {
  met: { icon: "✓", label: "Met", className: "bg-emerald-100 text-emerald-700" },
  partial: { icon: "◐", label: "Partly met", className: "bg-amber-100 text-amber-700" },
  not_met: { icon: "✗", label: "Not met", className: "bg-rose-100 text-rose-700" },
} as const;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-slate-100 px-6 py-5">
      <h3 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function formatTime(d: Date | null): string {
  return d ? d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "";
}

function IdentityCard({ identity, revealedAt, byYou }: { identity: RevealedIdentity; revealedAt: Date | null; byYou: boolean }) {
  const empty = !identity.name && !identity.email && !identity.phone && !identity.location && identity.links.length === 0;
  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 p-4">
      {empty ? (
        <p className="text-sm text-slate-700">No name or contact details were found in this resume.</p>
      ) : (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          {identity.name && (
            <>
              <dt className="text-slate-500">Name</dt>
              <dd className="font-semibold text-slate-900">{identity.name}</dd>
            </>
          )}
          {identity.email && (
            <>
              <dt className="text-slate-500">Email</dt>
              <dd>
                <a className="text-indigo-700 hover:underline" href={`mailto:${identity.email}`}>
                  {identity.email}
                </a>
              </dd>
            </>
          )}
          {identity.phone && (
            <>
              <dt className="text-slate-500">Phone</dt>
              <dd>{identity.phone}</dd>
            </>
          )}
          {identity.location && (
            <>
              <dt className="text-slate-500">Location</dt>
              <dd>{identity.location}</dd>
            </>
          )}
          {identity.links.length > 0 && (
            <>
              <dt className="text-slate-500">Links</dt>
              <dd className="space-y-0.5">
                {identity.links.map((l) => (
                  <a
                    key={l}
                    className="block truncate text-indigo-700 hover:underline"
                    href={/^https?:\/\//.test(l) ? l : `https://${l}`}
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    {l}
                  </a>
                ))}
              </dd>
            </>
          )}
        </dl>
      )}
      <p className="mt-3 text-xs text-slate-500">
        Revealed by {byYou ? "you" : "another user"}
        {revealedAt ? ` at ${formatTime(revealedAt)}` : ""}. This reveal is logged.
      </p>
    </div>
  );
}

function Checklist({ verdicts, job }: { verdicts: RequirementVerdict[]; job: Job }) {
  const reqs = requirementMap(job.requirements);
  if (verdicts.length === 0) return <p className="text-sm text-slate-500">None listed for this job.</p>;
  return (
    <ul className="space-y-3">
      {verdicts.map((v) => {
        const style = VERDICT[v.verdict];
        const req = reqs.get(v.req_id);
        return (
          <li key={v.req_id} className="flex gap-3">
            <span
              className={`flex size-6 shrink-0 items-center justify-center rounded-full text-sm font-bold ${style.className}`}
              role="img"
              aria-label={style.label}
              title={style.label}
            >
              {style.icon}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-slate-900">{req?.text ?? v.req_id}</p>
              {v.evidence && <p className="mt-0.5 text-xs text-slate-500">{v.evidence}</p>}
            </div>
            {req && <span className="shrink-0 text-xs text-slate-400 tabular-nums" title="Tag weight (1–5)">×{tagWeight(req)}</span>}
          </li>
        );
      })}
    </ul>
  );
}

const DECISIONS: { value: Decision; label: string }[] = [
  { value: "scored", label: "To review" },
  { value: "shortlisted", label: "Shortlist" },
  { value: "rejected", label: "Reject" },
];

export function CandidateDrawer({ candidate: c, job, actions, currentUid, onClose, showLabel = false }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [revealResult, setRevealResult] = useState<{ identity: RevealedIdentity; at: Date | null; by: string | null } | null>(null);

  useEffect(() => {
    setError(null);
    setRevealResult(null);
    setConfirming(false);
  }, [c.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !confirming && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, confirming]);

  const decided = c.status === "scored" || c.status === "shortlisted" || c.status === "rejected";
  const identity = c.revealed ?? revealResult?.identity ?? null;
  const revealedAt = c.revealedAt ?? revealResult?.at ?? null;
  const revealedBy = c.revealedBy ?? revealResult?.by ?? null;
  const canReveal = c.status === "shortlisted";

  async function decide(status: Decision) {
    if (status === c.status) return;
    setBusy(status);
    setError(null);
    try {
      await actions.setStatus(c.id, status);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function retry() {
    setBusy("retry");
    setError(null);
    try {
      await actions.retry!(c.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function reveal() {
    setBusy("reveal");
    setError(null);
    try {
      const r = await actions.reveal(c.id);
      setRevealResult({ identity: r.identity, at: r.revealedAt, by: r.revealedBy });
      setConfirming(false);
    } catch (e) {
      setError((e as Error).message);
      setConfirming(false);
    } finally {
      setBusy(null);
    }
  }

  const s = c.score;
  const ev = c.evaluation;
  const p = c.profile;
  const w = job.weights;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      <div className="absolute inset-0 bg-slate-900/30" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-2xl flex-col overflow-y-auto bg-white shadow-2xl">
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 px-6 py-4 backdrop-blur">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <h2 id="drawer-title" className="font-mono text-lg font-semibold text-slate-900">
                  {c.anonId}
                </h2>
                <StatusChip status={c.status} />
              </div>
              {p?.headline && <p className="mt-1 text-sm text-slate-600">{p.headline}</p>}
            </div>
            <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
              ✕
            </Button>
          </div>

          {decided && (
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <div className="inline-flex rounded-lg bg-slate-100 p-1" role="group" aria-label="Decision">
                {DECISIONS.map((d) => (
                  <button
                    key={d.value}
                    type="button"
                    onClick={() => decide(d.value)}
                    disabled={busy !== null}
                    aria-pressed={c.status === d.value}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                      c.status === d.value
                        ? d.value === "shortlisted"
                          ? "bg-emerald-600 text-white shadow-sm"
                          : d.value === "rejected"
                            ? "bg-rose-600 text-white shadow-sm"
                            : "bg-white text-slate-900 shadow-sm"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {busy === d.value ? <Spinner className="size-4" /> : d.label}
                  </button>
                ))}
              </div>
              {!identity && (
                <span title={canReveal ? undefined : "Shortlist this candidate to reveal their identity."}>
                  <Button variant="secondary" size="sm" disabled={!canReveal || busy !== null} onClick={() => setConfirming(true)}>
                    Reveal identity
                  </Button>
                </span>
              )}
            </div>
          )}
          {decided && !identity && !canReveal && (
            <p className="mt-2 text-xs text-slate-500">Identity stays hidden until you shortlist this candidate.</p>
          )}
          {error && (
            <div className="mt-3">
              <Alert>{error}</Alert>
            </div>
          )}
        </header>

        {identity && (
          <div className="px-6 pt-5">
            <IdentityCard identity={identity} revealedAt={revealedAt} byYou={revealedBy === currentUid || currentUid === null} />
          </div>
        )}

        {c.status === "processing" && (
          <div className="flex items-center gap-3 px-6 py-10 text-sm text-slate-500">
            <Spinner /> Parsing, anonymising and evaluating this resume…
          </div>
        )}
        {c.status === "failed" && (
          <div className="space-y-3 px-6 py-6">
            <Alert tone="warning">{c.error ?? "Processing failed."}</Alert>
            {actions.retry && actions.canRetry?.(c.id) ? (
              <Button onClick={retry} loading={busy === "retry"}>
                Retry this resume
              </Button>
            ) : (
              actions.retry && (
                <p className="text-xs text-slate-500">
                  Retry works from the browser tab that uploaded this resume, while it stays open, because PDFs are never
                  stored on the server. Otherwise, upload the PDF again.
                </p>
              )
            )}
          </div>
        )}

        {s && ev && (
          <>
            <Section title="Score">
              <div className="flex items-end gap-6">
                <div>
                  <p className="text-4xl font-bold tracking-tight text-slate-900 tabular-nums">{s.total.toFixed(0)}</p>
                  <p className="text-xs text-slate-500">out of 100</p>
                </div>
                {s.missing_must_have && (
                  <span className="mb-1 rounded-full bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700 ring-1 ring-rose-200 ring-inset">
                    Missing at least one must-have
                  </span>
                )}
              </div>
              <div className="mt-4 space-y-3">
                {[
                  { label: "Must-have tags", value: s.must_have, weight: w.must },
                  { label: "Nice-to-have tags", value: s.nice_to_have, weight: w.nice },
                  { label: "Semantic match to the job", value: s.semantic, weight: w.semantic },
                ].map((row) => (
                  <div key={row.label}>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-700">{row.label}</span>
                      <span className="text-slate-500 tabular-nums">
                        {percent(row.value)} <span className="text-xs">· weight {percent(row.weight)}</span>
                      </span>
                    </div>
                    <ScoreBar value={row.value} max={1} className="mt-1" label={row.label} />
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs text-slate-400">
                Computed in code from the weighted checklist below and an embedding similarity (raw cosine{" "}
                {s.semantic_raw.toFixed(3)}). Institution names are never scored.
              </p>
            </Section>

            <Section title="Must-have tags">
              <Checklist verdicts={ev.must_have} job={job} />
            </Section>
            <Section title="Nice-to-have tags">
              <Checklist verdicts={ev.nice_to_have} job={job} />
            </Section>

            <Section title="Assessment">
              <p className="text-sm text-slate-800">{ev.summary}</p>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div>
                  <p className="text-xs font-medium text-emerald-700">Strengths</p>
                  <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
                    {ev.strengths.length ? ev.strengths.map((x) => <li key={x}>{x}</li>) : <li className="list-none text-slate-400">–</li>}
                  </ul>
                </div>
                <div>
                  <p className="text-xs font-medium text-rose-700">Gaps</p>
                  <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
                    {ev.gaps.length ? ev.gaps.map((x) => <li key={x}>{x}</li>) : <li className="list-none text-slate-400">–</li>}
                  </ul>
                </div>
              </div>
            </Section>
          </>
        )}

        {p && (
          <>
            <Section title="Blind profile">
              <div className="flex flex-wrap gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">
                  <svg className="size-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path fillRule="evenodd" d="M10 1.944A11.954 11.954 0 0 1 2.166 5C2.056 5.649 2 6.319 2 7c0 5.225 3.34 9.67 8 11.317C14.66 16.67 18 12.225 18 7c0-.682-.057-1.35-.166-2.001A11.954 11.954 0 0 1 10 1.944Z" clipRule="evenodd" />
                  </svg>
                  {c.redactionCount} identity detail{c.redactionCount === 1 ? "" : "s"} redacted
                </span>
                {c.photoPresent && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-800">
                    Photo detected and hidden
                  </span>
                )}
                {showLabel && c.label && (
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">Dataset: {labelName(c.label)}</span>
                )}
                {p.total_experience_months !== null && (
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">
                    {formatMonths(p.total_experience_months)} experience
                  </span>
                )}
              </div>
            </Section>

            {p.education.length > 0 && (
              <Section title="Education">
                <ul className="space-y-3">
                  {p.education.map((e, i) => (
                    <li key={i} className="text-sm">
                      <p className="font-medium text-slate-900">{[e.degree, e.field].filter(Boolean).join(", ") || "Education"}</p>
                      <p className="text-slate-600">
                        {[e.institution, e.grade, [e.start_year, e.end_year].filter(Boolean).join("–")].filter(Boolean).join(" · ")}
                      </p>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {p.experience.length > 0 && (
              <Section title="Experience">
                <ol className="relative space-y-5 border-l border-slate-200 pl-5">
                  {p.experience.map((e, i) => (
                    <li key={i} className="relative">
                      <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-white bg-indigo-500" />
                      <p className="text-sm font-medium text-slate-900">
                        {e.title ?? "Role"}
                        {e.organisation && <span className="font-normal text-slate-600"> · {e.organisation}</span>}
                      </p>
                      <p className="text-xs text-slate-500">
                        {[e.start, e.end].filter(Boolean).join(" – ")}
                        {e.months ? ` (${formatMonths(e.months)})` : ""}
                      </p>
                      {e.summary && <p className="mt-1 text-sm text-slate-700">{e.summary}</p>}
                    </li>
                  ))}
                </ol>
              </Section>
            )}

            {p.skills.length > 0 && (
              <Section title="Skills">
                <div className="flex flex-wrap gap-1.5">
                  {p.skills.map((x) => (
                    <span key={x} className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                      {x}
                    </span>
                  ))}
                </div>
              </Section>
            )}

            {p.projects.length > 0 && (
              <Section title="Projects">
                <ul className="space-y-3">
                  {p.projects.map((x, i) => (
                    <li key={i} className="text-sm">
                      <p className="font-medium text-slate-900">{x.title}</p>
                      <p className="text-slate-700">{x.summary}</p>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {p.certifications.length > 0 && (
              <Section title="Certifications">
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {p.certifications.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </Section>
            )}
          </>
        )}
        <div className="h-8 shrink-0" />
      </aside>

      <ConfirmDialog
        open={confirming}
        title={`Reveal ${c.anonId}'s identity?`}
        confirmLabel="Reveal identity"
        busy={busy === "reveal"}
        onConfirm={reveal}
        onCancel={() => setConfirming(false)}
      >
        You'll see this candidate's name and contact details. <strong>This is logged</strong> with your account and the time,
        and the candidate stays revealed.
      </ConfirmDialog>
    </div>
  );
}
