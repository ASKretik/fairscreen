import { collection, onSnapshot, query, where } from "firebase/firestore";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useAuth } from "../auth/AuthContext";
import { Alert, Card, PageSpinner } from "../components/ui";
import { toJob } from "../lib/convert";
import { db } from "../lib/db";
import type { Job } from "../types";

export function Jobs() {
  const { user } = useAuth();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!db || !user) return;
    // Equality filter only, sorted here: a where + orderBy query would need a composite index.
    const q = query(collection(db, "jobs"), where("ownerUid", "==", user.uid));
    return onSnapshot(
      q,
      (snap) => {
        const list = snap.docs.map((d) => toJob(d.id, d.data()));
        list.sort((a, b) => (b.createdAt?.getTime() ?? 0) - (a.createdAt?.getTime() ?? 0));
        setJobs(list);
      },
      (e) => setError(e.message),
    );
  }, [user]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">My jobs</h1>
        <Link to="/jobs/new" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700">
          New job
        </Link>
      </div>
      {error && <Alert>Couldn't load your jobs: {error}</Alert>}
      {!jobs && !error && <PageSpinner />}
      {jobs?.length === 0 && (
        <Card className="p-10 text-center">
          <p className="font-medium text-slate-900">No jobs yet</p>
          <p className="mt-1 text-sm text-slate-500">Create a job from a job description to start screening resumes.</p>
          <Link to="/jobs/new" className="mt-4 inline-block text-sm font-semibold text-indigo-600 hover:text-indigo-700">
            Create your first job →
          </Link>
        </Card>
      )}
      {jobs && jobs.length > 0 && (
        <ul className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {jobs.map((j) => (
            <li key={j.id}>
              <Link to={`/jobs/${j.id}`} className="block h-full">
                <Card className="h-full p-5 transition-shadow hover:shadow-md">
                  <h2 className="font-semibold text-slate-900">{j.title}</h2>
                  <p className="mt-0.5 text-xs text-slate-500">
                    Created {j.createdAt ? j.createdAt.toLocaleDateString(undefined, { dateStyle: "medium" }) : "–"}
                  </p>
                  <div className="mt-4 flex gap-5 text-sm">
                    <span>
                      <span className="font-semibold tabular-nums">{j.counts?.total ?? 0}</span> <span className="text-slate-500">candidates</span>
                    </span>
                    <span>
                      <span className="font-semibold tabular-nums">{j.counts?.shortlisted ?? 0}</span> <span className="text-slate-500">shortlisted</span>
                    </span>
                    {(j.counts?.processing ?? 0) > 0 && <span className="text-sky-700">{j.counts.processing} processing</span>}
                  </div>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
