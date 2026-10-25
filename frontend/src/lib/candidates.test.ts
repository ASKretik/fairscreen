import { describe, expect, it } from "vitest";
import { loadDemo } from "../test-fixtures";
import type { Candidate } from "../types";
import { combine, coverage, formatMonths, rankCandidates, rankMap, rebalance, rescore, topMatches } from "./candidates";

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
    const { candidates } = loadDemo();
    const semanticOnly = rescore(candidates, { must: 0, nice: 0, semantic: 1 });
    semanticOnly.forEach((c, i) => expect(c.score!.total).toBeCloseTo(100 * candidates[i].score!.semantic));
  });
});
