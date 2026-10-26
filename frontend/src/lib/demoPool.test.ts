import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { rankCandidates } from "./candidates";
import { deriveWorkspace, labelName, rescaleCosine, roleSetup, topLabels, type DemoPool } from "./demoPool";

const profile = (headline: string, skills: string[]) => ({
  headline, education: [], experience: [], total_experience_months: null, skills, projects: [], certifications: [],
});

const POOL: DemoPool = {
  version: 2,
  semantic: { lo: 0.5, hi: 0.9 },
  weights: { must: 0.5, nice: 0.2, semantic: 0.3 },
  roles: [
    { id: "it", title: "IT Admin", category: "INFORMATION-TECHNOLOGY", must: ["a", "b"], nice: ["c"] },
    { id: "fin", title: "Analyst", category: "FINANCE", must: ["d"], nice: [] },
  ],
  tags: [
    { id: "a", text: "Active Directory", kind: "skill", group: "it" },
    { id: "b", text: "Networking", kind: "skill", group: "it" },
    { id: "c", text: "PowerShell", kind: "skill", group: "it" },
    { id: "d", text: "Budgeting", kind: "experience", group: "fin" },
  ],
  candidates: [
    { id: "c1", anonId: "CAND-0001", label: "INFORMATION-TECHNOLOGY", profile: profile("Sysadmin", ["Kubernetes"]), photoPresent: false, redactionCount: 2,
      summary: "s1", verdicts: { a: { verdict: "met", evidence: "AD" }, b: { verdict: "met", evidence: "LAN" } }, cosine: { it: 0.8, fin: 0.5 } },
    { id: "c2", anonId: "CAND-0002", label: "FINANCE", profile: profile("Analyst", ["Excel"]), photoPresent: false, redactionCount: 0,
      summary: "s2", verdicts: { d: { verdict: "met", evidence: "budgets" }, c: { verdict: "partial", evidence: "VBA" } }, cosine: { it: 0.55, fin: 0.85 } },
    { id: "c3", anonId: "CAND-0003", label: "SYNTHETIC", profile: profile("Helpdesk", []), photoPresent: false, redactionCount: 5,
      summary: "s3", verdicts: { a: { verdict: "partial", evidence: "some AD" } }, cosine: { it: 0.7, fin: 0.6 } },
  ],
  identities: { c3: { name: "Sam Example (synthetic)", email: null, phone: null, links: [], location: null } },
};
const none = { status: {}, revealed: {} };

describe("demo pool", () => {
  it("scores the pool with the backend formula for a role's defaults", () => {
    const setup = roleSetup(POOL, "it");
    expect(setup.must.map((t) => [t.id, t.weight])).toEqual([["a", 3], ["b", 3]]);
    const { job, candidates } = deriveWorkspace(POOL, setup, none);
    expect(job.requirements.must_have.map((r) => r.id)).toEqual(["a", "b"]);
    const c1 = candidates.find((c) => c.id === "c1")!;
    expect(c1.score!.must_have).toBe(1);
    expect(c1.score!.semantic).toBeCloseTo(0.75);
    expect(c1.score!.total).toBeCloseTo(100 * (0.5 * 1 + 0.2 * 0 + 0.3 * 0.75));
    expect(candidates.find((c) => c.id === "c2")!.score!.missing_must_have).toBe(true);
    expect(rankCandidates(candidates)[0].id).toBe("c1");
  });

  it("tags, weights and roles change the ranking", () => {
    const it = roleSetup(POOL, "it");
    const powershellHeavy = { ...it, must: [], nice: [{ ...it.nice[0], weight: 5 }], weights: { must: 0, nice: 1, semantic: 0 } };
    expect(rankCandidates(deriveWorkspace(POOL, powershellHeavy, none).candidates)[0].id).toBe("c2");
    expect(rankCandidates(deriveWorkspace(POOL, roleSetup(POOL, "fin"), none).candidates)[0].id).toBe("c2");
  });

  it("typed-in tags are keyword-matched against the blind profile", () => {
    const setup = { ...roleSetup(POOL, "it"), must: [{ id: "k1", text: "Kubernetes", kind: "skill" as const, weight: 3, custom: true }] };
    const c1 = deriveWorkspace(POOL, setup, none).candidates.find((c) => c.id === "c1")!;
    expect(c1.evaluation!.must_have[0]).toMatchObject({ req_id: "k1", verdict: "met" });
  });

  it("keeps decisions and reveals, and summarises the top labels", () => {
    const at = new Date();
    const { candidates, job } = deriveWorkspace(POOL, roleSetup(POOL, "it"), {
      status: { c3: "shortlisted" },
      revealed: { c3: { identity: POOL.identities.c3, at } },
    });
    const c3 = candidates.find((c) => c.id === "c3")!;
    expect(c3.status).toBe("shortlisted");
    expect(c3.revealed?.name).toContain("synthetic");
    expect(job.counts.shortlisted).toBe(1);
    expect(topLabels(candidates, 2).map((t) => t.label)).toContain("INFORMATION-TECHNOLOGY");
    expect(labelName("INFORMATION-TECHNOLOGY")).toBe("IT");
    expect(labelName("BUSINESS-DEVELOPMENT")).toBe("Business development");
    expect(rescaleCosine(0.95, 0.5, 0.9)).toBe(1);
  });

  it("the published pool file is well-formed and blind", () => {
    const pool = JSON.parse(readFileSync(new URL("../../public/demo/demo_pool.json", import.meta.url), "utf8")) as DemoPool;
    const tagIds = new Set(pool.tags.map((t) => t.id));
    expect(pool.version).toBe(2);
    expect(pool.candidates.length).toBeGreaterThan(0);
    expect(pool.candidates.length).toBeLessThanOrEqual(100);
    for (const role of pool.roles) for (const id of [...role.must, ...role.nice]) expect(tagIds.has(id)).toBe(true);
    for (const c of pool.candidates) {
      expect(Object.keys(c.verdicts).every((id) => tagIds.has(id))).toBe(true);
      expect(c).not.toHaveProperty("identity");
      expect(c).not.toHaveProperty("fileName");
    }
    // Only synthetic (fictional) people can be revealed.
    for (const id of Object.keys(pool.identities)) expect(pool.candidates.find((c) => c.id === id)?.label).toBe("SYNTHETIC");
    const derived = deriveWorkspace(pool, roleSetup(pool, pool.roles[0].id), { status: {}, revealed: {} });
    expect(derived.candidates.every((c) => c.score && c.score.total >= 0 && c.score.total <= 100)).toBe(true);
  });
});
