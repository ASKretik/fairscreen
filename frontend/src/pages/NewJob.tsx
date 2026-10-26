import { useState } from "react";
import { useNavigate } from "react-router";
import { newRequirement, RequirementEditor, validateRequirements } from "../components/RequirementEditor";
import { Alert, Button, Card } from "../components/ui";
import { api } from "../lib/api";
import { useServerStatus } from "../lib/serverStatus";
import type { JobRequirements } from "../types";

const MIN_JD = 50;
type Mode = "jd" | "tags";

const emptyTags = (): JobRequirements => ({
  role_title: "",
  must_have: [newRequirement("m")],
  nice_to_have: [],
  min_years_experience: null,
  education_requirement: null,
});

const inputClass =
  "mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 focus:outline-none";

export function NewJob() {
  const navigate = useNavigate();
  const { status } = useServerStatus();
  const [mode, setMode] = useState<Mode>("jd");
  const [title, setTitle] = useState("");
  const [jd, setJd] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [extracted, setExtracted] = useState<JobRequirements | null>(null);
  const [draft, setDraft] = useState<JobRequirements | null>(null);
  const [ownTags, setOwnTags] = useState<JobRequirements>(emptyTags);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function extract() {
    setBusy(true);
    setError(null);
    try {
      const job = await api.createJob(title.trim(), { jdText: jd });
      setJobId(job.id);
      setExtracted(job.requirements);
      setDraft(job.requirements);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!jobId || !draft) return;
    const problem = validateRequirements(draft);
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      if (JSON.stringify(draft) !== JSON.stringify(extracted)) await api.updateRequirements(jobId, draft);
      navigate(`/jobs/${jobId}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  async function createFromTags() {
    const requirements = { ...ownTags, role_title: ownTags.role_title.trim() || title.trim() };
    const problem = !title.trim() ? "Add a job title." : validateRequirements(requirements);
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      const job = await api.createJob(title.trim(), { requirements });
      navigate(`/jobs/${job.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  const waking = busy && status !== "ok" && (
    <Alert tone="info">The screening server is waking up; the first request can take up to a minute.</Alert>
  );

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">New job</h1>
        <p className="mt-1 text-sm text-slate-600">
          {draft
            ? "Step 2 of 2: check the extracted tags and set their weights."
            : mode === "jd"
              ? "Step 1 of 2: paste the job description, and FairScreen turns it into screening tags."
              : "Write the tags every resume will be checked against, and how much each one matters."}
        </p>
      </div>

      {!draft && (
        <div className="inline-flex rounded-lg bg-slate-100 p-1" role="tablist" aria-label="How to set up tags">
          {(
            [
              ["jd", "From a job description"],
              ["tags", "Write your own tags"],
            ] as const
          ).map(([m, label]) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              onClick={() => {
                setMode(m);
                setError(null);
              }}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                mode === m ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {draft ? (
        <Card className="space-y-6 p-6">
          <Alert tone="info">
            These tags were extracted by AI from your job description. Edit anything that's wrong, add your own and set each
            tag's weight. Tags lock once you upload the first resumes; weights can change at any time.
          </Alert>
          <RequirementEditor value={draft} onChange={setDraft} />
          {error && <Alert>{error}</Alert>}
          <div className="flex justify-end">
            <Button onClick={save} loading={busy}>
              Save job
            </Button>
          </div>
        </Card>
      ) : (
        <Card className="space-y-5 p-6">
          <label className="block">
            <span className="text-sm font-semibold text-slate-900">Job title</span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              placeholder="e.g. IT Systems Administrator"
              className={inputClass}
            />
          </label>
          {mode === "jd" ? (
            <>
              <label className="block">
                <span className="text-sm font-semibold text-slate-900">Job description</span>
                <textarea
                  value={jd}
                  onChange={(e) => setJd(e.target.value)}
                  rows={14}
                  maxLength={20000}
                  placeholder="Paste the full job description, including requirements and nice-to-haves."
                  className={`${inputClass} leading-relaxed`}
                />
                <span className="mt-1 block text-xs text-slate-400">
                  {jd.length < MIN_JD ? `At least ${MIN_JD} characters` : `${jd.length.toLocaleString()} characters`}
                </span>
              </label>
              {error && <Alert>{error}</Alert>}
              {waking}
              <div className="flex justify-end">
                <Button onClick={extract} loading={busy} disabled={!title.trim() || jd.trim().length < MIN_JD}>
                  {busy ? "Extracting tags…" : "Extract tags"}
                </Button>
              </div>
            </>
          ) : (
            <>
              <RequirementEditor value={ownTags} onChange={setOwnTags} />
              {error && <Alert>{error}</Alert>}
              {waking}
              <div className="flex justify-end">
                <Button onClick={createFromTags} loading={busy} disabled={!title.trim()}>
                  Create job
                </Button>
              </div>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
