// The preloaded demo (public/demo/demo_pool.json, written by backend/scripts/build_demo.py).
// Every resume was judged once against every library tag, so any choice of tags and weights is
// scored here in the browser, with the same formula as the backend and no API calls.

import type {
  BlindProfile,
  Candidate,
  CandidateEvaluation,
  Decision,
  Job,
  JobRequirements,
  ReqKind,
  Requirement,
  RequirementVerdict,
  RevealedIdentity,
  Verdict,
  Weights,
} from "../types";
import { combine, DEFAULT_TAG_WEIGHT, tagWeightMap, weightedCoverage } from "./candidates";
import { keywordVerdict } from "./keywords";

export const MAX_TAGS_PER_GROUP = 8;

export interface PoolTag {
  id: string;
  text: string;
  kind: ReqKind;
  /** Role ID, or "general". */
  group: string;
}

export interface PoolRole {
  id: string;
  title: string;
  /** The dataset category this role's resumes come from. */
  category?: string;
  must: string[];
  nice: string[];
}

export interface PoolCandidate {
  id: string;
  anonId: string;
  label: string;
  profile: BlindProfile;
  photoPresent: boolean;
  redactionCount: number;
  summary: string;
  /** Library tag ID -> verdict; a library tag missing here was judged not met. */
  verdicts: Record<string, { verdict: Verdict; evidence: string }>;
  /** Role ID -> raw cosine between the profile and the role's tags. */
  cosine: Record<string, number>;
}

export interface DemoPool {
  version: number;
  placeholder?: boolean;
  generatedAt?: string;
  source?: string;
  semantic: { lo: number; hi: number };
  weights: Weights;
  roles: PoolRole[];
  tags: PoolTag[];
  candidates: PoolCandidate[];
  /** Identities the demo may reveal once shortlisted (synthetic people only). */
  identities: Record<string, RevealedIdentity>;
}

export interface ActiveTag {
  id: string;
  text: string;
  kind: ReqKind;
  weight: number;
  /** Typed in by the viewer: matched by keywords, not judged by the AI. */
  custom: boolean;
}

export interface DemoSetup {
  roleId: string;
  must: ActiveTag[];
  nice: ActiveTag[];
  weights: Weights;
}

export interface DemoDecisions {
  status: Record<string, Decision>;
  revealed: Record<string, { identity: RevealedIdentity; at: Date }>;
}

export const DEMO_USER = "demo-user";

/** The role's default tags at weight 3, with the default group weights. */
export function roleSetup(pool: DemoPool, roleId: string): DemoSetup {
  const role = pool.roles.find((r) => r.id === roleId) ?? pool.roles[0];
  const byId = new Map(pool.tags.map((t) => [t.id, t]));
  const active = (ids: string[]): ActiveTag[] =>
    ids
      .map((id) => byId.get(id))
      .filter((t): t is PoolTag => Boolean(t))
      .map((t) => ({ id: t.id, text: t.text, kind: t.kind, weight: DEFAULT_TAG_WEIGHT, custom: false }));
  return { roleId: role.id, must: active(role.must), nice: active(role.nice), weights: { ...pool.weights } };
}

export function rescaleCosine(cosine: number, lo: number, hi: number): number {
  return hi > lo ? Math.min(1, Math.max(0, (cosine - lo) / (hi - lo))) : 0;
}

function verdictFor(c: PoolCandidate, tag: ActiveTag): RequirementVerdict {
  if (tag.custom) return { req_id: tag.id, ...keywordVerdict(tag.text, c.profile) };
  const v = c.verdicts[tag.id];
  return v ? { req_id: tag.id, verdict: v.verdict, evidence: v.evidence } : { req_id: tag.id, verdict: "not_met", evidence: "" };
}

function evaluation(c: PoolCandidate, setup: DemoSetup): CandidateEvaluation {
  const must = setup.must.map((t) => verdictFor(c, t));
  const nice = setup.nice.map((t) => verdictFor(c, t));
  const text = new Map([...setup.must, ...setup.nice].map((t) => [t.id, t.text]));
  const pick = (vs: RequirementVerdict[], verdict: Verdict) => vs.filter((v) => v.verdict === verdict).map((v) => text.get(v.req_id)!);
  return {
    must_have: must,
    nice_to_have: nice,
    strengths: [...pick(must, "met"), ...pick(nice, "met")].slice(0, 3),
    gaps: [
      ...pick(must, "not_met").map((t) => `Missing: ${t}`),
      ...pick(must, "partial").map((t) => `Partly shown: ${t}`),
      ...pick(nice, "not_met").map((t) => `Missing: ${t}`),
    ].slice(0, 3),
    summary: c.summary,
  };
}

export function setupRequirements(pool: DemoPool, setup: DemoSetup): JobRequirements {
  const role = pool.roles.find((r) => r.id === setup.roleId) ?? pool.roles[0];
  const req = (t: ActiveTag): Requirement => ({ id: t.id, text: t.text, kind: t.kind, weight: t.weight });
  return {
    role_title: role.title,
    must_have: setup.must.map(req),
    nice_to_have: setup.nice.map(req),
    min_years_experience: null,
    education_requirement: null,
  };
}

/** The pool as a job and its candidates, scored for this setup: what JobWorkspace renders. */
export function deriveWorkspace(pool: DemoPool, setup: DemoSetup, decisions: DemoDecisions): { job: Job; candidates: Candidate[] } {
  const requirements = setupRequirements(pool, setup);
  const weights = tagWeightMap(requirements);
  const { lo, hi } = pool.semantic;
  const candidates: Candidate[] = pool.candidates.map((c) => {
    const ev = evaluation(c, setup);
    const must = weightedCoverage(ev.must_have, weights);
    const nice = weightedCoverage(ev.nice_to_have, weights);
    const raw = c.cosine[setup.roleId] ?? 0;
    const semantic = rescaleCosine(raw, lo, hi);
    const revealed = decisions.revealed[c.id];
    return {
      id: c.id,
      anonId: c.anonId,
      fileName: `${c.anonId}.pdf`,
      status: decisions.status[c.id] ?? "scored",
      error: null,
      profile: c.profile,
      evaluation: ev,
      score: {
        must_have: must,
        nice_to_have: nice,
        semantic,
        semantic_raw: raw,
        total: combine(must, nice, semantic, setup.weights),
        missing_must_have: ev.must_have.some((v) => v.verdict === "not_met"),
      },
      photoPresent: c.photoPresent,
      redactionCount: c.redactionCount,
      revealed: revealed?.identity ?? null,
      revealedAt: revealed?.at ?? null,
      revealedBy: revealed ? DEMO_USER : null,
      createdAt: null,
      updatedAt: null,
      label: c.label,
    };
  });
  const shortlisted = candidates.filter((c) => c.status === "shortlisted").length;
  const job: Job = {
    id: "demo-pool",
    title: requirements.role_title,
    jdText: "",
    requirements,
    requirementsLocked: true,
    weights: setup.weights,
    counts: { total: candidates.length, processing: 0, scored: candidates.length, failed: 0, shortlisted },
    createdAt: null,
    updatedAt: null,
  };
  return { job, candidates };
}

const LABELS: Record<string, string> = {
  "INFORMATION-TECHNOLOGY": "IT",
  FINANCE: "Finance",
  HR: "HR",
  SYNTHETIC: "Synthetic",
};

/** Short display name for a dataset category, e.g. "INFORMATION-TECHNOLOGY" -> "IT". */
export function labelName(label: string | null | undefined): string {
  if (!label) return "–";
  return LABELS[label] ?? label.charAt(0) + label.slice(1).toLowerCase().replace(/-/g, " ");
}

/** How many of the top `n` candidates (by score) carry each label, largest first. */
export function topLabels(candidates: Candidate[], n: number): { label: string; count: number }[] {
  const top = [...candidates]
    .filter((c) => c.score)
    .sort((a, b) => b.score!.total - a.score!.total || a.anonId.localeCompare(b.anonId))
    .slice(0, n);
  const counts = new Map<string, number>();
  top.forEach((c) => counts.set(c.label ?? "", (counts.get(c.label ?? "") ?? 0) + 1));
  return [...counts].map(([label, count]) => ({ label, count })).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}
