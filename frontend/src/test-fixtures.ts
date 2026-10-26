import { readFileSync } from "node:fs";
import { toCandidate, toJob } from "./lib/convert";
import type { Candidate, Job } from "./types";

/** A sample job with fictional candidates (the original single-job demo), used as a realistic fixture. */
export function loadDemo(): { job: Job; candidates: Candidate[] } {
  const raw = JSON.parse(readFileSync(new URL("./test-data/sample_job.json", import.meta.url), "utf8"));
  return {
    job: toJob(raw.job.id, raw.job),
    candidates: raw.candidates.map((c: { id: string }) => toCandidate(c.id, c)),
  };
}
