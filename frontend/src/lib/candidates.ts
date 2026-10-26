import type { Candidate, Education, JobRequirements, Requirement, RequirementVerdict, Verdict, Weights } from "../types";

export const DEFAULT_TAG_WEIGHT = 3;
export const TAG_WEIGHTS = [1, 2, 3, 4, 5] as const;
const VERDICT_VALUE: Record<Verdict, number> = { met: 1, partial: 0.5, not_met: 0 };

export const tagWeight = (r: Pick<Requirement, "weight"> | undefined): number => r?.weight ?? DEFAULT_TAG_WEIGHT;

/** Tag weights by requirement ID. */
export function tagWeightMap(req: JobRequirements): Map<string, number> {
  return new Map([...req.must_have, ...req.nice_to_have].map((r) => [r.id, tagWeight(r)]));
}

/**
 * Same formula as backend scoring.coverage: the weighted mean of verdict values (met 1, partial
 * 0.5), 1 with no requirements. Equal weights give (met + 0.5 * partial) / n.
 */
export function weightedCoverage(verdicts: RequirementVerdict[], weights: Map<string, number>): number {
  if (verdicts.length === 0) return 1;
  let num = 0;
  let den = 0;
  for (const v of verdicts) {
    const w = weights.get(v.req_id) ?? DEFAULT_TAG_WEIGHT;
    num += w * VERDICT_VALUE[v.verdict];
    den += w;
  }
  return den > 0 ? num / den : 1;
}

/** Each tag's share of the total score (0–1), given the group weights. */
export function tagShares(req: JobRequirements, w: Weights): Map<string, number> {
  const shares = new Map<string, number>();
  for (const [items, groupWeight] of [[req.must_have, w.must], [req.nice_to_have, w.nice]] as const) {
    const sum = items.reduce((s, r) => s + tagWeight(r), 0);
    items.forEach((r) => shares.set(r.id, sum ? (groupWeight * tagWeight(r)) / sum : 0));
  }
  return shares;
}

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

/**
 * Candidates rescored for (preview) group and tag weights, from their checklists: no API call.
 * Same as backend scoring.rescore.
 */
export function rescore(cands: Candidate[], w: Weights, req: JobRequirements): Candidate[] {
  const weights = tagWeightMap(req);
  return cands.map((c) => {
    if (!c.score || !c.evaluation) return c;
    const must = weightedCoverage(c.evaluation.must_have, weights);
    const nice = weightedCoverage(c.evaluation.nice_to_have, weights);
    return { ...c, score: { ...c.score, must_have: must, nice_to_have: nice, total: combine(must, nice, c.score.semantic, w) } };
  });
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
