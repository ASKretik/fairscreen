import type { Decision, JobRequirements, RevealResult, Weights } from "../types";
import { toDate } from "./convert";
import { API_URL } from "./env";
import { auth } from "./firebase";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function describe(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    // FastAPI validation errors: [{loc, msg}, ...]
    return detail.map((d) => (d as { msg?: string }).msg ?? "Invalid input").join(" ");
  }
  return `Request failed (${status}).`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await auth?.currentUser?.getIdToken();
  if (!token) throw new ApiError(401, "Sign in required.");
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new ApiError(0, "Can't reach the screening server. Check your connection and try again.");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, describe(body?.detail, res.status));
  return body as T;
}

function json(method: string, data?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
  };
}

export const api = {
  /** From a JD (tags are extracted by AI) or from the recruiter's own tags (no AI call). */
  createJob(title: string, source: { jdText: string } | { requirements: JobRequirements }) {
    const body = "jdText" in source ? { title, jd_text: source.jdText } : { title, requirements: source.requirements };
    return request<{ id: string; requirements: JobRequirements }>("/jobs", json("POST", body));
  },

  updateRequirements(jobId: string, requirements: JobRequirements) {
    return request<JobRequirements>(`/jobs/${jobId}/requirements`, json("PATCH", requirements));
  },

  async uploadResumes(jobId: string, files: File[]) {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const res = await request<{ candidate_ids: string[] }>(`/jobs/${jobId}/resumes`, { method: "POST", body: form });
    return res.candidate_ids;
  },

  /** Re-run a failed candidate; the same PDF goes up again because PDFs are never stored. */
  async retryCandidate(jobId: string, candidateId: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    await request(`/jobs/${jobId}/candidates/${candidateId}/retry`, { method: "POST", body: form });
  },

  async updateWeights(jobId: string, weights: Weights, tagWeights: Record<string, number>) {
    await request(`/jobs/${jobId}/weights`, json("PATCH", { ...weights, tag_weights: tagWeights }));
  },

  async deleteJob(jobId: string) {
    const token = await auth?.currentUser?.getIdToken();
    if (!token) throw new ApiError(401, "Sign in required.");
    const res = await fetch(`${API_URL}/jobs/${jobId}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new ApiError(res.status, describe(body?.detail, res.status));
    }
  },

  async setStatus(jobId: string, candidateId: string, status: Decision) {
    await request(`/jobs/${jobId}/candidates/${candidateId}/status`, json("POST", { status }));
  },

  async reveal(jobId: string, candidateId: string): Promise<RevealResult> {
    const res = await request<{ identity: RevealResult["identity"]; revealedAt: string; revealedBy: string }>(
      `/jobs/${jobId}/candidates/${candidateId}/reveal`,
      { method: "POST" },
    );
    return { identity: res.identity, revealedAt: toDate(res.revealedAt), revealedBy: res.revealedBy };
  },
};

/** GET /health without auth; resolves true when the server answers (wakes Render). */
export async function checkHealth(timeoutMs = 90_000): Promise<boolean> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}/health`, { signal: ctrl.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}
