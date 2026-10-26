import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { JobWorkspace } from "../components/JobWorkspace";
import { PrimaryCta } from "../components/Layout";
import { TagStudio } from "../components/TagStudio";
import { Alert, Card, PageSpinner } from "../components/ui";
import { DEMO_USER, deriveWorkspace, roleSetup, type DemoDecisions, type DemoPool, type DemoSetup } from "../lib/demoPool";
import { publicUrl } from "../lib/env";
import { workspaceEnabled } from "../lib/firebase";
import type { Decision, WorkspaceActions } from "../types";

const NO_DECISIONS: DemoDecisions = { status: {}, revealed: {} };
const NO_IDENTITY = { name: null, email: null, phone: null, links: [], location: null };

/**
 * The live demo: a preloaded pool from public/demo/demo_pool.json, ranked in the browser for
 * whatever tags and weights the viewer picks. No login, no API calls (SPEC §10).
 */
export function Demo() {
  const [pool, setPool] = useState<DemoPool | null>(null);
  const [setup, setSetup] = useState<DemoSetup | null>(null);
  const [decisions, setDecisions] = useState<DemoDecisions>(NO_DECISIONS);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(publicUrl("demo/demo_pool.json"))
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<DemoPool>;
      })
      .then((data) => {
        setPool(data);
        setSetup(roleSetup(data, data.roles[0].id));
      })
      .catch((e) => setError(`Couldn't load the demo data (${e.message}).`));
  }, []);

  const derived = useMemo(() => (pool && setup ? deriveWorkspace(pool, setup, decisions) : null), [pool, setup, decisions]);

  const actions = useMemo<WorkspaceActions>(
    () => ({
      async setStatus(id: string, status: Decision) {
        setDecisions((d) => ({ ...d, status: { ...d.status, [id]: status } }));
      },
      async reveal(id: string) {
        const c = derived?.candidates.find((x) => x.id === id);
        if (!c) throw new Error("Candidate not found.");
        if (c.revealed) return { identity: c.revealed, revealedAt: c.revealedAt, revealedBy: c.revealedBy };
        if (c.status !== "shortlisted") throw new Error("Shortlist the candidate before revealing their identity.");
        const identity = pool?.identities[id] ?? NO_IDENTITY;
        const at = new Date();
        setDecisions((d) => ({ ...d, revealed: { ...d.revealed, [id]: { identity, at } } }));
        return { identity, revealedAt: at, revealedBy: DEMO_USER };
      },
    }),
    [derived, pool],
  );

  if (error) return <Alert>{error}</Alert>;
  if (!pool || !setup || !derived) return <PageSpinner label="Loading demo…" />;
  const synthetic = Object.keys(pool.identities).length;
  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-semibold text-indigo-600">Live demo</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
          {pool.placeholder
            ? "Try screening with your own tags"
            : `Screen ${pool.candidates.length} preloaded resumes with your own tags`}
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          {pool.placeholder
            ? "Placeholder data: a few fictional candidates, until the preloaded resume pool is built."
            : `${pool.source ?? "Public resumes"}. Each was anonymised and checked by AI against every library tag in advance.`}{" "}
          Change the role, the tags or their weights and the ranking updates instantly in your browser. Open a candidate to
          see the evidence, shortlist them, and reveal{synthetic ? " a synthetic candidate's" : " their"} identity. Nothing is
          saved or sent anywhere.
        </p>
      </div>
      <TagStudio
        pool={pool}
        setup={setup}
        candidates={derived.candidates}
        onChange={setSetup}
        onRoleChange={(roleId) => {
          setSetup(roleSetup(pool, roleId));
          setDecisions(NO_DECISIONS);
        }}
      />
      <JobWorkspace
        key={setup.roleId}
        job={derived.job}
        candidates={derived.candidates}
        actions={actions}
        currentUid={DEMO_USER}
        demo
        showLabels
      />
      <Card className="flex flex-col items-start justify-between gap-4 p-6 sm:flex-row sm:items-center">
        <div>
          <h2 className="font-semibold text-slate-900">Ready to screen your own role?</h2>
          <p className="mt-1 text-sm text-slate-600">
            {workspaceEnabled
              ? "Create a job from a description or your own tags, upload up to 20 PDFs and get a blind shortlist. Free during early access."
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
