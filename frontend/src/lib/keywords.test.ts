import { describe, expect, it } from "vitest";
import { loadDemo } from "../test-fixtures";
import type { BlindProfile } from "../types";
import { keywords, keywordVerdict } from "./keywords";

const profile: BlindProfile = {
  headline: "Systems administrator, 6 yrs, Windows/Linux",
  education: [{ institution: "Kubernetes Institute of Technology", degree: "BSc", field: "Computer Science", grade: null, start_year: null, end_year: 2016 }],
  experience: [
    { title: "IT Administrator", organisation: "Payroll Corp", start: "2018", end: "present", months: 70, summary: "Managed Active Directory and Group Policy for 400 users." },
  ],
  total_experience_months: 70,
  skills: ["PowerShell", "VMware vSphere", "C#", ".NET"],
  projects: [{ title: "Backup automation", summary: "Automated nightly backups with scripts." }],
  certifications: ["CompTIA Network+"],
};

describe("keyword matching for viewer-typed tags", () => {
  it("drops stop words and bare numbers", () => {
    expect(keywords("5+ years of experience with VMware and PowerShell")).toEqual(["vmware", "powershell"]);
    expect(keywords("C# or .NET, TCP/IP")).toEqual(["c#", ".net", "tcp", "ip"]);
    expect(keywords("experience")).toEqual([]);
  });

  it("met when every keyword appears, partial for at least half", () => {
    expect(keywordVerdict("PowerShell scripting", profile).verdict).toBe("partial");
    expect(keywordVerdict("PowerShell", profile)).toMatchObject({ verdict: "met" });
    expect(keywordVerdict("Active Directory", profile).evidence).toContain("Managed Active Directory");
    expect(keywordVerdict("backup", profile).verdict).toBe("met"); // plural "backups"
    expect(keywordVerdict("Network+ certification", profile).verdict).toBe("partial");
    expect(keywordVerdict("Salesforce CRM", profile)).toEqual({ verdict: "not_met", evidence: "" });
  });

  it("never matches institution or employer names", () => {
    expect(keywordVerdict("Kubernetes", profile).verdict).toBe("not_met");
    expect(keywordVerdict("payroll", profile).verdict).toBe("not_met");
  });

  it("works on real fixture profiles", () => {
    const { candidates } = loadDemo();
    expect(keywordVerdict("Active Directory", candidates[0].profile!).verdict).toBe("met");
  });
});
