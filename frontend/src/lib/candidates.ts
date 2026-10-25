import type { Candidate, Education, JobRequirements, Requirement, RequirementVerdict, Weights } from "../types";

const DECIDED = new Set(["scored", "shortlisted", "rejected"]);

/** Has a score and is not processing/failed. */
export function isScored(c: Candidate): boolean {
  return c.score !== null && DECIDED.has(c.status);
}

export interface Coverage {
  met: number;
  partial: number;
  total: number;
}

export function coverage(verdicts: RequirementVerdict[] | undefined): Coverage {
  const list = verdicts ?? [];
  return {
    met: list.filter((v) => v.verdict === "met").length,
    partial: list.filter((v) => v.verdict === "partial").length,
    total: list.length,
  };
}

const PENDING_ORDER: Record<string, number> = { processing: 0, failed: 1 };

/** Scored candidates by score (desc), then processing, then failed. */
export function rankCandidates(cands: Candidate[], direction: "desc" | "asc" = "desc"): Candidate[] {
  const scored = cands.filter(isScored).sort((a, b) => {
    const diff = (b.score?.total ?? 0) - (a.score?.total ?? 0);
    return (direction === "desc" ? diff : -diff) || a.anonId.localeCompare(b.anonId);
  });
  const pending = cands
    .filter((c) => !isScored(c))
    .sort((a, b) => (PENDING_ORDER[a.status] ?? 2) - (PENDING_ORDER[b.status] ?? 2) || a.anonId.localeCompare(b.anonId));
  return [...scored, ...pending];
}

/** Rank by score among scored candidates, independent of the table's filter and sort. */
export function rankMap(cands: Candidate[]): Map<string, number> {
  const ranks = new Map<string, number>();
  rankCandidates(cands).filter(isScored).forEach((c, i) => ranks.set(c.id, i + 1));
  return ranks;
}

export function requirementMap(req: JobRequirements): Map<string, Requirement> {
  return new Map([...req.must_have, ...req.nice_to_have].map((r) => [r.id, r]));
}

/** Up to `n` met requirements, must-haves and skills first. */
export function topMatches(c: Candidate, req: JobRequirements, n = 2): string[] {
  if (!c.evaluation) return [];
  const byId = requirementMap(req);
  const met = [...c.evaluation.must_have, ...c.evaluation.nice_to_have]
    .filter((v) => v.verdict === "met")
    .map((v) => byId.get(v.req_id))
    .filter((r): r is Requirement => Boolean(r));
  const skillsFirst = [...met.filter((r) => r.kind === "skill"), ...met.filter((r) => r.kind !== "skill")];
  return skillsFirst.slice(0, n).map((r) => r.text);
}

export function topGap(c: Candidate): string | null {
  return c.evaluation?.gaps[0] ?? null;
}

/** The first education entry, as the resume lists it. */
export function primaryEducation(c: Candidate): Education | null {
  return c.profile?.education[0] ?? null;
}

export function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`;
}

export function formatMonths(months: number | null | undefined): string {
  if (months === null || months === undefined) return "";
  const y = Math.floor(months / 12);
  const m = months % 12;
  const parts = [];
  if (y) parts.push(`${y} yr${y > 1 ? "s" : ""}`);
  if (m || !y) parts.push(`${m} mo${m === 1 ? "" : "s"}`);
  return parts.join(" ");
}

export function percent(x: number | null | undefined): string {
  return x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`;
}

/** Same formula as backend scoring.combine (SPEC §7.4). */
export function combine(must: number, nice: number, semantic: number, w: Weights): number {
  return Math.min(100, Math.max(0, 100 * (w.must * must + w.nice * nice + w.semantic * semantic)));
}

/** Candidates with score.total recomputed for preview weights (no API call). */
export function rescore(cands: Candidate[], w: Weights): Candidate[] {
  return cands.map((c) =>
    c.score ? { ...c, score: { ...c.score, total: combine(c.score.must_have, c.score.nice_to_have, c.score.semantic, w) } } : c,
  );
}

/**
 * Set slider `index` to `value` (whole percents) and scale the other two so all three
 * still sum to 100. Rounding error goes to the last of the others.
 */
export function rebalance(percents: [number, number, number], index: number, value: number): [number, number, number] {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  const others = [0, 1, 2].filter((i) => i !== index);
  const rest = 100 - v;
  const sum = others.reduce((s, i) => s + percents[i], 0);
  const out: [number, number, number] = [...percents];
  out[index] = v;
  if (sum === 0) {
    out[others[0]] = Math.floor(rest / 2);
    out[others[1]] = rest - out[others[0]];
  } else {
    out[others[0]] = Math.round((percents[others[0]] * rest) / sum);
    out[others[1]] = rest - out[others[0]];
  }
  return out;
}
