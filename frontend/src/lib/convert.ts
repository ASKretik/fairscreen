import type { Candidate, Job } from "../types";

type Raw = Record<string, unknown>;

/** Firestore Timestamp, ISO string (demo JSON / API responses) or Date → Date. */
export function toDate(value: unknown): Date | null {
  if (!value) return null;
  if (value instanceof Date) return value;
  if (typeof value === "string" || typeof value === "number") {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  if (typeof (value as { toDate?: unknown }).toDate === "function") {
    return (value as { toDate(): Date }).toDate();
  }
  return null;
}

export function toJob(id: string, data: Raw): Job {
  const { jdEmbedding: _ignored, ...rest } = data;
  return {
    ...(rest as unknown as Job),
    id,
    createdAt: toDate(data.createdAt),
    updatedAt: toDate(data.updatedAt),
  };
}

export function toCandidate(id: string, data: Raw): Candidate {
  return {
    ...(data as unknown as Candidate),
    id,
    revealedAt: toDate(data.revealedAt),
    createdAt: toDate(data.createdAt),
    updatedAt: toDate(data.updatedAt),
  };
}
