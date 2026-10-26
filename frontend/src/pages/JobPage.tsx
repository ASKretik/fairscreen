import { collection, doc, onSnapshot } from "firebase/firestore";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useAuth } from "../auth/AuthContext";
import { JobWorkspace } from "../components/JobWorkspace";
import { Alert, PageSpinner } from "../components/ui";
import { api } from "../lib/api";
import { toCandidate, toJob } from "../lib/convert";
import { db } from "../lib/db";
import type { Candidate, Job, WorkspaceActions } from "../types";

export function JobPage() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [job, setJob] = useState<Job | null | undefined>(undefined);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Files uploaded from this tab, by candidate ID, kept only until that candidate is scored, so a
  // failed one can be retried. They stay in the browser and are never rendered.
  const sessionFiles = useRef(new Map<string, File>());

  useEffect(() => {
    candidates.forEach((c) => {
      if (c.status !== "failed" && c.status !== "processing") sessionFiles.current.delete(c.id);
    });
  }, [candidates]);

  useEffect(() => {
    if (!db) return;
    const offJob = onSnapshot(
      doc(db, "jobs", jobId),
      (snap) => setJob(snap.exists() ? toJob(snap.id, snap.data()) : null),
      // A job you don't own is denied by the security rules; treat it as not found.
      () => setJob(null),
    );
    const offCands = onSnapshot(
      collection(db, "jobs", jobId, "candidates"),
      (snap) => setCandidates(snap.docs.map((d) => toCandidate(d.id, d.data()))),
      (e) => setError(e.code === "permission-denied" ? null : e.message),
    );
    return () => {
      offJob();
      offCands();
    };
  }, [jobId]);

  const actions = useMemo<WorkspaceActions>(
    () => ({
      setStatus: (id, status) => api.setStatus(jobId, id, status),
      reveal: (id) => api.reveal(jobId, id),
      upload: async (files) => {
        const ids = await api.uploadResumes(jobId, files);
        ids.forEach((id, i) => files[i] && sessionFiles.current.set(id, files[i]));
        return ids;
      },
      canRetry: (id) => sessionFiles.current.has(id),
      retry: async (id) => {
        const file = sessionFiles.current.get(id);
        if (!file) throw new Error("Upload this resume again to retry it; PDFs aren't stored.");
        await api.retryCandidate(jobId, id, file);
      },
      saveRequirements: async (req) => {
        await api.updateRequirements(jobId, req);
      },
      saveWeights: (w, tagWeights) => api.updateWeights(jobId, w, tagWeights),
      deleteJob: async () => {
        await api.deleteJob(jobId);
        navigate("/jobs");
      },
    }),
    [jobId, navigate],
  );

  if (job === undefined) return <PageSpinner />;
  if (job === null) {
    return (
      <div className="py-16 text-center">
        <p className="font-medium text-slate-900">Job not found</p>
        <Link to="/jobs" className="mt-2 inline-block text-sm text-indigo-600">
          Back to my jobs
        </Link>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <Link to="/jobs" className="text-sm text-slate-500 hover:text-slate-800">
        ← My jobs
      </Link>
      {error && <Alert>{error}</Alert>}
      <JobWorkspace job={job} candidates={candidates} actions={actions} currentUid={user?.uid ?? null} />
    </div>
  );
}
