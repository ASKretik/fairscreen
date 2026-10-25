import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { rankCandidates, rankMap } from "../lib/candidates";
import { loadDemo } from "../test-fixtures";
import type { WorkspaceActions } from "../types";
import { CandidateDrawer } from "./CandidateDrawer";
import { CandidateTable } from "./CandidateTable";

const noop: WorkspaceActions = {
  setStatus: async () => {},
  reveal: async () => ({ identity: { name: null, email: null, phone: null, links: [], location: null }, revealedAt: null, revealedBy: null }),
};

describe("blind rendering (SPEC §16: no identity in the table)", () => {
  const { job, candidates } = loadDemo();
  const identityStrings = candidates.flatMap((c) => [
    c.fileName,
    ...(c.revealed ? [c.revealed.name, c.revealed.email, c.revealed.phone, c.revealed.location, ...c.revealed.links] : []),
  ]).filter((s): s is string => Boolean(s));

  it("the ranked table never shows names, contact details or file names, even after reveal", () => {
    const html = renderToStaticMarkup(
      <CandidateTable rows={rankCandidates(candidates)} ranks={rankMap(candidates)} requirements={job.requirements}
        sortDir="desc" onSort={() => {}} onOpen={() => {}} selectedId={null} />,
    );
    for (const s of identityStrings) expect(html).not.toContain(s);
    for (const c of candidates) expect(html).toContain(c.anonId);
  });

  it("the drawer hides identity until reveal, and shows it after", () => {
    const hidden = candidates.find((c) => !c.revealed)!;
    const html = renderToStaticMarkup(<CandidateDrawer candidate={hidden} job={job} actions={noop} currentUid="u" onClose={() => {}} />);
    for (const s of identityStrings) expect(html).not.toContain(s);
    expect(html).toContain("identity detail");

    const shown = candidates.find((c) => c.revealed)!;
    const revealedHtml = renderToStaticMarkup(<CandidateDrawer candidate={shown} job={job} actions={noop} currentUid="demo-user" onClose={() => {}} />);
    expect(revealedHtml).toContain(shown.revealed!.name!);
    expect(revealedHtml).toContain("Revealed by you");
    expect(revealedHtml).not.toContain(shown.fileName);
  });

  it("reveal is disabled until the candidate is shortlisted", () => {
    const scored = candidates.find((c) => c.status === "scored")!;
    const html = renderToStaticMarkup(<CandidateDrawer candidate={scored} job={job} actions={noop} currentUid="u" onClose={() => {}} />);
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Reveal identity<\/button>/);
    expect(html).toContain("Identity stays hidden until you shortlist");
  });
});
