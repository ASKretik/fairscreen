import { describe, expect, it } from "vitest";
import { loadDemo } from "../test-fixtures";
import type { Candidate } from "../types";
import {
  combine,
  coverage,
  formatMonths,
  rankCandidates,
  rankMap,
  rebalance,
  rescore,
  tagShares,
  tagWeightMap,
  topMatches,
  weightedCoverage,
} from "./candidates";

describe("candidate helpers", () => {
  const { job, candidates } = loadDemo();

  it("ranks scored candidates by score, with processing and failed last", () => {
    const processing: Candidate = { ...candidates[0], id: "p", anonId: "CAND-0000", status: "processing", score: null, evaluation: null };
    const failed: Candidate = { ...processing, id: "f", anonId: "CAND-0001", status: "failed" };
    const ranked = rankCandidates([failed, ...candidates, processing]);
    const totals = ranked.filter((c) => c.score).map((c) => c.score!.total);
    expect(totals).toEqual([...totals].sort((a, b) => b - a));
    expect(ranked.slice(-2).map((c) => c.status)).toEqual(["processing", "failed"]);
    expect(rankCandidates(candidates, "asc")[0].anonId).toBe("CAND-81B7");
    expect(rankMap([failed, ...candidates]).get("f")).toBeUndefined();
  });

  it("counts coverage", () => {
    expect(coverage(candidates[0].evaluation!.must_have)).toEqual({ met: 6, partial: 0, total: 6 });
    expect(coverage(undefined)).toEqual({ met: 0, partial: 0, total: 0 });
  });

  it("lists matched skill requirements first", () => {
    const matches = topMatches(candidates[0], job.requirements);
    expect(matches).toHaveLength(2);
    expect(matches[0]).toBe("Windows Server and Active Directory administration");
  });

  it("formats months", () => {
    expect(formatMonths(123)).toBe("10 yrs 3 mos");
    expect(formatMonths(12)).toBe("1 yr");
    expect(formatMonths(5)).toBe("5 mos");
    expect(formatMonths(null)).toBe("");
  });
});


describe("weights", () => {
  it("rebalance keeps the sum at 100 and scales the others proportionally", () => {
    expect(rebalance([50, 20, 30], 0, 70)).toEqual([70, 12, 18]);
    expect(rebalance([50, 20, 30], 2, 100)).toEqual([0, 0, 100]);
    expect(rebalance([0, 0, 100], 2, 40)).toEqual([30, 30, 40]);
    for (const [i, v] of [[0, 33], [1, 77], [2, 5]] as const) {
      expect(rebalance([45, 25, 30], i, v).reduce((a, b) => a + b, 0)).toBe(100);
    }
  });

  it("combine and rescore match the backend formula", () => {
    expect(combine(0.625, 0.5, 0.5, { must: 0.5, nice: 0.2, semantic: 0.3 })).toBeCloseTo(56.25);
    const { job, candidates } = loadDemo();
    const semanticOnly = rescore(candidates, { must: 0, nice: 0, semantic: 1 }, job.requirements);
    semanticOnly.forEach((c, i) => expect(c.score!.total).toBeCloseTo(100 * candidates[i].score!.semantic));
    // Equal tag weights reproduce the stored (SPEC §7.4) scores exactly.
    rescore(candidates, job.weights, job.requirements).forEach((c, i) => expect(c.score!.total).toBeCloseTo(candidates[i].score!.total));
  });
});

describe("tag weights", () => {
  const v = (req_id: string, verdict: "met" | "partial" | "not_met") => ({ req_id, verdict, evidence: "" });

  it("weighted coverage matches backend scoring.coverage", () => {
    const verdicts = [v("m1", "met"), v("m2", "partial"), v("m3", "not_met"), v("m4", "met")];
    expect(weightedCoverage(verdicts, new Map())).toBeCloseTo(2.5 / 4);
    expect(weightedCoverage([v("m1", "met"), v("m2", "not_met")], new Map([["m1", 5], ["m2", 1]]))).toBeCloseTo(5 / 6);
    expect(weightedCoverage([v("m1", "met"), v("m2", "not_met")], new Map([["m1", 1]]))).toBeCloseTo(1 / 4);
    expect(weightedCoverage([], new Map())).toBe(1);
  });

  it("raising a tag's weight moves candidates who have it up", () => {
    const { job, candidates } = loadDemo();
    const target = job.requirements.must_have[4]; // virtualization
    const heavy = { ...job.requirements, must_have: job.requirements.must_have.map((r) => (r.id === target.id ? { ...r, weight: 5 } : { ...r, weight: 1 })) };
    const before = rescore(candidates, job.weights, job.requirements);
    const after = rescore(candidates, job.weights, heavy);
    before.forEach((c, i) => {
      const met = c.evaluation!.must_have.find((x) => x.req_id === target.id)!.verdict === "met";
      if (met) expect(after[i].score!.must_have).toBeGreaterThanOrEqual(c.score!.must_have - 1e-9);
      else expect(after[i].score!.must_have).toBeLessThanOrEqual(c.score!.must_have + 1e-9);
    });
    expect(tagWeightMap(heavy).get(target.id)).toBe(5);
  });

  it("tag shares split each group's weight by tag weight", () => {
    const { job } = loadDemo();
    const shares = tagShares(job.requirements, { must: 0.5, nice: 0.2, semantic: 0.3 });
    const total = [...shares.values()].reduce((a, b) => a + b, 0);
    expect(total).toBeCloseTo(0.7);
    expect(shares.get("m1")).toBeCloseTo(0.5 / job.requirements.must_have.length);
  });
});
