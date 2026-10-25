import { describe, expect, it } from "vitest";
import { loadDemo } from "../test-fixtures";
import { rankCandidates } from "./candidates";
import { candidatesToCsv, csvFileName } from "./csv";

describe("candidatesToCsv", () => {
  const { candidates } = loadDemo();
  const rows = rankCandidates(candidates);
  const csv = candidatesToCsv(rows);
  const lines = csv.trim().split("\r\n");

  it("has a header and one line per candidate, in rank order", () => {
    expect(lines).toHaveLength(candidates.length + 1);
    expect(lines[0]).toContain('"Anon ID"');
    expect(lines[1].startsWith('"1","CAND-3F9A"')).toBe(true);
  });

  it("includes name, email and file name only for revealed candidates", () => {
    const revealed = candidates.filter((c) => c.revealed);
    const hidden = candidates.filter((c) => !c.revealed);
    expect(revealed.length).toBeGreaterThan(0);
    for (const c of revealed) {
      const line = lines.find((l) => l.includes(c.anonId))!;
      expect(line).toContain(c.revealed!.name!);
      expect(line).toContain(c.revealed!.email!);
      expect(line).toContain(c.fileName);
    }
    for (const c of hidden) {
      const line = lines.find((l) => l.includes(c.anonId))!;
      expect(line).not.toContain(c.fileName);
      expect(line.endsWith('"","",""')).toBe(true); // name, email, file name left empty
    }
  });

  it("escapes quotes and defuses spreadsheet formulas", () => {
    const [c] = candidates;
    const tricky = { ...c, anonId: '=HYPERLINK("x")', revealed: null };
    const out = candidatesToCsv([tricky]);
    expect(out).toContain(`"'=HYPERLINK(""x"")"`);
  });

  it("builds a safe file name", () => {
    expect(csvFileName("IT Systems Admin / Ops!", new Date("2026-10-27T10:00:00Z"))).toBe("fairscreen-it-systems-admin-ops-2026-10-27.csv");
  });
});
