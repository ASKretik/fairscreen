import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { JobWorkspace } from "../components/JobWorkspace";
import { PrimaryCta } from "../components/Layout";
import { Alert, Card, PageSpinner } from "../components/ui";
import { rescore } from "../lib/candidates";
import { toCandidate, toJob } from "../lib/convert";
import { publicUrl } from "../lib/env";
import { workspaceEnabled } from "../lib/firebase";
import type { Candidate, Decision, Job, RevealedIdentity, Weights, WorkspaceActions } from "../types";

interface DemoFile {
  placeholder?: boolean;
  job: Record<string, unknown> & { id: string };
  candidates: (Record<string, unknown> & { id: string })[];
  /** Identities the demo may reveal once a candidate is shortlisted (synthetic people only). */
  demoIdentities?: Record<string, RevealedIdentity>;
}

const DEMO_USER = "demo-user";

/** Read-only demo from public/demo/demo_job.json: no login, no API calls (SPEC §10). */
export function Demo() {
  const [job, setJob] = useState<Job | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [identities, setIdentities] = useState<Record<string, RevealedIdentity>>({});
  const [placeholder, setPlaceholder] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(publicUrl("demo/demo_job.json"))
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<DemoFile>;
      })
      .then((data) => {
        setJob(toJob(data.job.id, data.job));
        setCandidates(data.candidates.map((c) => toCandidate(c.id, c)));
        setIdentities(data.demoIdentities ?? {});
        setPlaceholder(Boolean(data.placeholder));
      })
      .catch((e) => setError(`Couldn't load the demo data (${e.message}).`));
  }, []);

  const actions = useMemo<WorkspaceActions>(
    () => ({
      async saveWeights(w: Weights) {
        setJob((j) => (j ? { ...j, weights: w } : j));
        setCandidates((cs) => rescore(cs, w));
      },
      async setStatus(id: string, status: Decision) {
        setCandidates((cs) => cs.map((c) => (c.id === id ? { ...c, status } : c)));
      },
      async reveal(id: string) {
        const c = candidates.find((x) => x.id === id);
        if (!c) throw new Error("Candidate not found.");
        if (c.revealed) return { identity: c.revealed, revealedAt: c.revealedAt, revealedBy: c.revealedBy };
        if (c.status !== "shortlisted") throw new Error("Shortlist the candidate before revealing their identity.");
        const identity = identities[id] ?? { name: null, email: null, phone: null, links: [], location: null };
        const now = new Date();
        setCandidates((cs) => cs.map((x) => (x.id === id ? { ...x, revealed: identity, revealedAt: now, revealedBy: DEMO_USER } : x)));
        return { identity, revealedAt: now, revealedBy: DEMO_USER };
      },
    }),
    [candidates, identities],
  );

  if (error) return <Alert>{error}</Alert>;
  if (!job) return <PageSpinner label="Loading demo…" />;
  return (
    <div className="space-y-4">
      <Alert tone="info">
        <strong>Interactive demo.</strong>{" "}
        {placeholder
          ? "A sample IT role with fictional candidates. "
          : "Real screening output for a sample IT role, on public and synthetic (fictional) resumes. "}
        Open a candidate, shortlist, reject, adjust the weights and reveal a shortlisted candidate. Nothing is saved and nothing
        is sent to a server; uploads are off.
      </Alert>
      <JobWorkspace job={job} candidates={candidates} actions={actions} currentUid={DEMO_USER} demo />
      <Card className="flex flex-col items-start justify-between gap-4 p-6 sm:flex-row sm:items-center">
        <div>
          <h2 className="font-semibold text-slate-900">Ready to screen your own role?</h2>
          <p className="mt-1 text-sm text-slate-600">
            {workspaceEnabled
              ? "Paste your job description, upload up to 20 PDFs and get a blind shortlist. Free during early access."
              : "Recruiter workspaces are opening soon. Free during early access."}
          </p>
        </div>
        {workspaceEnabled ? (
          <PrimaryCta />
        ) : (
          <Link to={{ pathname: "/", hash: "pricing" }} className="text-sm font-semibold text-indigo-600 hover:text-indigo-700">
            See plans →
          </Link>
        )}
      </Card>
    </div>
  );
}
