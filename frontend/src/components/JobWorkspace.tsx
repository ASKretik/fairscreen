import { useMemo, useState } from "react";
import { rankCandidates, rankMap, rescore, tagWeight } from "../lib/candidates";
import { candidatesToCsv, csvFileName, downloadCsv } from "../lib/csv";
import type { Candidate, CandidateStatus, Job, JobRequirements, Requirement, Weights, WorkspaceActions } from "../types";
import { CandidateDrawer } from "./CandidateDrawer";
import { ConfirmDialog } from "./ConfirmDialog";
import { CandidateTable } from "./CandidateTable";
import { RequirementEditor, validateRequirements } from "./RequirementEditor";
import { StatusChip, STATUS_LABELS } from "./StatusChip";
import { Alert, Button, Card } from "./ui";
import { UploadDropzone } from "./UploadDropzone";
import { WeightSliders } from "./WeightSliders";

const MAX_CANDIDATES = 50;
const PAGE = 25;
type Filter = "all" | CandidateStatus;
const FILTERS: Filter[] = ["all", "scored", "shortlisted", "rejected", "processing", "failed"];

interface Props {
  job: Job;
  candidates: Candidate[];
  actions: WorkspaceActions;
  currentUid: string | null;
  demo?: boolean;
  /** Show each candidate's dataset label (demo pool only). */
  showLabels?: boolean;
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-2xl font-semibold text-slate-900 tabular-nums">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}

function TagChip({ r, must }: { r: Requirement; must: boolean }) {
  const w = tagWeight(r);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full py-1 pr-1.5 pl-2.5 text-xs font-medium ${
        must ? "bg-indigo-600 text-white" : "text-indigo-700 ring-1 ring-indigo-200 ring-inset"
      }`}
      title={`${r.kind} · weight ${w} of 5`}
    >
      {r.text}
      <span className={`rounded-full px-1.5 text-[10px] tabular-nums ${must ? "bg-white/20" : "bg-indigo-50"}`}>×{w}</span>
    </span>
  );
}

function RequirementsPanel({ job, actions }: { job: Job; actions: WorkspaceActions }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<JobRequirements>(job.requirements);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const req = job.requirements;
  const editable = Boolean(actions.saveRequirements) && !job.requirementsLocked;

  async function save() {
    const problem = validateRequirements(draft);
    if (problem) return setError(problem);
    setSaving(true);
    setError(null);
    try {
      await actions.saveRequirements!(draft);
      setEditing(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <Card className="p-6">
        <RequirementEditor value={draft} onChange={setDraft} />
        {error && <div className="mt-4"><Alert>{error}</Alert></div>}
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setEditing(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={save} loading={saving}>
            Save tags
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-xs font-medium text-slate-500">Must-have</span>
        {req.must_have.map((r) => (
          <TagChip key={r.id} r={r} must />
        ))}
      </div>
      {req.nice_to_have.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-xs font-medium text-slate-500">Nice-to-have</span>
          {req.nice_to_have.map((r) => (
            <TagChip key={r.id} r={r} must={false} />
          ))}
        </div>
      )}
      {editable && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setDraft(job.requirements);
            setEditing(true);
          }}
        >
          Edit tags
        </Button>
      )}
      {job.requirementsLocked && actions.saveWeights && (
        <p className="text-xs text-slate-400">Tags are locked because screening has started; you can still change their weights.</p>
      )}
    </div>
  );
}

export function JobWorkspace({ job: savedJob, candidates: savedCandidates, actions, currentUid, demo = false, showLabels = false }: Props) {
  // While weights are being changed, everything below shows previewed scores.
  const [preview, setPreview] = useState<{ weights: Weights; requirements: JobRequirements } | null>(null);
  const job = useMemo(
    () => (preview ? { ...savedJob, weights: preview.weights, requirements: preview.requirements } : savedJob),
    [savedJob, preview],
  );
  const candidates = useMemo(
    () => (preview ? rescore(savedCandidates, preview.weights, preview.requirements) : savedCandidates),
    [savedCandidates, preview],
  );
  const [limit, setLimit] = useState(PAGE);
  const [showWeights, setShowWeights] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  // ?candidate=<id> opens that candidate's drawer (deep link).
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("candidate"),
  );
  const [batch, setBatch] = useState<string[]>([]);

  const ranks = useMemo(() => rankMap(candidates), [candidates]);
  const rows = useMemo(
    () => rankCandidates(candidates, sortDir).filter((c) => filter === "all" || c.status === filter),
    [candidates, sortDir, filter],
  );
  const visibleRows = rows.slice(0, limit);
  const counts = useMemo(() => {
    const m: Record<string, number> = { all: candidates.length };
    candidates.forEach((c) => (m[c.status] = (m[c.status] ?? 0) + 1));
    return m;
  }, [candidates]);
  const selected = candidates.find((c) => c.id === selectedId) ?? null;

  const batchCands = batch.map((id) => candidates.find((c) => c.id === id)).filter((c): c is Candidate => Boolean(c));
  const batchDone = batchCands.filter((c) => c.status !== "processing").length;
  const processing = counts.processing ?? 0;
  const retryable = candidates.filter((c) => c.status === "failed" && actions.canRetry?.(c.id));
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  async function retryFailed() {
    setRetrying(true);
    setRetryError(null);
    const results = await Promise.allSettled(retryable.map((c) => actions.retry!(c.id)));
    const failed = results.find((r): r is PromiseRejectedResult => r.status === "rejected");
    if (failed) setRetryError((failed.reason as Error).message);
    setRetrying(false);
  }

  async function upload(files: File[]) {
    const ids = await actions.upload!(files);
    setBatch(ids);
  }

  async function deleteJob() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await actions.deleteJob!();
    } catch (e) {
      setDeleteError((e as Error).message);
      setDeleting(false);
      setConfirmDelete(false);
    }
  }

  const hasScores = savedCandidates.some((c) => c.score);

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{job.title}</h1>
              {job.requirements.role_title && job.requirements.role_title !== job.title && (
                <p className="text-sm text-slate-500">{job.requirements.role_title}</p>
              )}
            </div>
            {!demo && <RequirementsPanel key={job.requirementsLocked ? "locked" : "open"} job={job} actions={actions} />}
          </div>
          <div className="shrink-0 space-y-4">
            <div className="grid grid-cols-4 gap-6 lg:text-right">
              <Stat label="Candidates" value={counts.all} />
              <Stat label="Scored" value={job.counts.scored} />
              <Stat label="Shortlisted" value={counts.shortlisted ?? 0} />
              <Stat label="Failed" value={counts.failed ?? 0} />
            </div>
            <div className="flex flex-wrap gap-2 lg:justify-end">
              {actions.saveWeights && hasScores && (
                <Button variant="secondary" size="sm" onClick={() => setShowWeights((v) => !v)} aria-expanded={showWeights}>
                  {showWeights ? "Hide weights" : "Adjust tag weights"}
                </Button>
              )}
              {actions.deleteJob && (
                <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
                  Delete job
                </Button>
              )}
            </div>
          </div>
        </div>
        {deleteError && <div className="mt-4"><Alert>{deleteError}</Alert></div>}
        {showWeights && actions.saveWeights && (
          <div className="mt-6 border-t border-slate-100 pt-6">
            <WeightSliders
              saved={savedJob.weights}
              requirements={savedJob.requirements}
              onPreview={setPreview}
              onSave={actions.saveWeights}
              blockedReason={processing > 0 ? "Wait until all resumes have finished processing." : null}
            />
          </div>
        )}
      </Card>

      {actions.upload && (
        <Card className="space-y-4 p-6">
          <h2 className="text-sm font-semibold text-slate-900">Add resumes</h2>
          <UploadDropzone remaining={MAX_CANDIDATES - candidates.length} locked={job.requirementsLocked} onUpload={upload} />
          {(batchCands.length > 0 || processing > 0) && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              {batchCands.length > 0 ? (
                <>
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-slate-700">
                      {batchDone === batchCands.length ? "Batch finished" : "Screening in progress"}
                    </span>
                    <span className="text-slate-500 tabular-nums">
                      {batchDone}/{batchCands.length}
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200">
                    <div className="h-full bg-indigo-500 transition-all" style={{ width: `${(batchDone / batchCands.length) * 100}%` }} />
                  </div>
                  {retryable.length > 0 && (
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      <Button size="sm" variant="secondary" onClick={retryFailed} loading={retrying}>
                        Retry {retryable.length} failed
                      </Button>
                      {retryError && <span className="text-xs text-rose-700">{retryError}</span>}
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {batchCands.map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => setSelectedId(c.id)}
                        className="inline-flex items-center gap-2 rounded-lg bg-white px-2 py-1 text-xs ring-1 ring-slate-200 hover:ring-indigo-300"
                      >
                        <span className="font-mono">{c.anonId}</span>
                        <StatusChip status={c.status} />
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-sm text-slate-600">{processing} resume(s) still processing…</p>
              )}
            </div>
          )}
        </Card>
      )}

      <Card className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-slate-200 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Filter by status">
            {FILTERS.filter((f) => f === "all" || f === "scored" || f === "shortlisted" || (counts[f] ?? 0) > 0).map((f) => (
              <button
                key={f}
                type="button"
                role="tab"
                aria-selected={filter === f}
                onClick={() => {
                  setFilter(f);
                  setLimit(PAGE);
                }}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                  filter === f ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {f === "all" ? "All" : STATUS_LABELS[f]} <span className="ml-0.5 opacity-60 tabular-nums">{counts[f] ?? 0}</span>
              </button>
            ))}
          </div>
          <Button
            variant="secondary"
            size="sm"
            disabled={rows.length === 0}
            onClick={() => downloadCsv(csvFileName(job.title), candidatesToCsv(rows, candidates))}
          >
            Export CSV
          </Button>
        </div>
        <CandidateTable
          rows={visibleRows}
          ranks={ranks}
          requirements={job.requirements}
          sortDir={sortDir}
          onSort={() => setSortDir((d) => (d === "desc" ? "asc" : "desc"))}
          onOpen={(c) => setSelectedId(c.id)}
          selectedId={selectedId}
          showLabels={showLabels}
        />
        {rows.length > visibleRows.length && (
          <div className="flex items-center justify-center gap-3 border-t border-slate-100 px-4 py-3">
            <span className="text-xs text-slate-500">
              Showing {visibleRows.length} of {rows.length}
            </span>
            <Button variant="secondary" size="sm" onClick={() => setLimit((n) => n + PAGE)}>
              Show {Math.min(PAGE, rows.length - visibleRows.length)} more
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setLimit(rows.length)}>
              Show all
            </Button>
          </div>
        )}
      </Card>

      {!demo && candidates.length === 0 && (
        <p className="text-center text-sm text-slate-500">Upload resumes above to start screening.</p>
      )}

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete "${savedJob.title}"?`}
        confirmLabel="Delete job"
        busy={deleting}
        onConfirm={deleteJob}
        onCancel={() => setConfirmDelete(false)}
      >
        This permanently deletes the job, all {savedCandidates.length} candidates and any revealed identities. It can't be undone.
      </ConfirmDialog>

      {selected && (
        <CandidateDrawer
          candidate={selected}
          job={job}
          actions={actions}
          currentUid={currentUid}
          onClose={() => setSelectedId(null)}
          showLabel={showLabels}
        />
      )}
    </div>
  );
}
