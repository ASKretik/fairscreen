import type { BlindProfile, Verdict } from "../types";
import { truncate } from "./candidates";

// Words that say nothing about what to look for in a resume.
const STOP = new Set(
  (
    "a an and or the of in on for with to at by from as is are be any other etc eg e.g ie i.e " +
    "experience experienced years year yrs plus least minimum min knowledge skill skills strong good solid " +
    "proven ability working work using use familiarity familiar understanding hands hands-on level " +
    "preferred required related field similar background expertise proficiency proficient advanced basic " +
    "excellent demonstrated relevant equivalent including such like"
  ).split(" "),
);

/** The words a custom tag is matched on: lower case, without stop words and bare numbers. */
export function keywords(text: string): string[] {
  const tokens = text.toLowerCase().split(/[^a-z0-9+#.]+/);
  const out: string[] = [];
  for (const raw of tokens) {
    const t = raw.replace(/^\.+(?=[^a-z])|\.+$/g, "");
    if (!t || STOP.has(t) || /^\d+\+?$/.test(t) || (t.length < 2 && t !== "c" && t !== "r")) continue;
    if (!out.includes(t)) out.push(t);
  }
  return out;
}

/** Blind text to search: no institution or employer names, so prestige can't count. */
function segments(p: BlindProfile): string[] {
  return [
    p.headline,
    ...p.skills,
    ...p.certifications,
    ...p.experience.flatMap((e) => [e.title ?? "", e.summary]),
    ...p.projects.flatMap((x) => [x.title, x.summary]),
    ...p.education.map((e) => [e.degree, e.field].filter(Boolean).join(" in ")),
  ].filter(Boolean);
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const pattern = (k: string) => new RegExp(`(?<![a-z0-9])${escape(k)}(?:s|es)?(?![a-z0-9])`, "i");

/**
 * Approximate verdict for a tag that wasn't judged by the AI: met when every keyword appears in
 * the blind profile, partial when at least half do. Evidence quotes the best-matching line.
 */
export function keywordVerdict(tag: string, profile: BlindProfile): { verdict: Verdict; evidence: string } {
  const words = keywords(tag);
  if (words.length === 0) return { verdict: "not_met", evidence: "" };
  const regexes = words.map(pattern);
  const lines = segments(profile);
  const found = words.filter((_, i) => lines.some((l) => regexes[i].test(l)));
  const ratio = found.length / words.length;
  const verdict: Verdict = ratio === 1 ? "met" : ratio >= 0.5 ? "partial" : "not_met";
  if (verdict === "not_met") return { verdict, evidence: "" };
  let best = "";
  let bestHits = 0;
  for (const l of lines) {
    const hits = regexes.filter((r) => r.test(l)).length;
    if (hits > bestHits) [best, bestHits] = [l, hits];
  }
  const snippet = truncate(best.split(/\s+/).slice(0, 18).join(" "), 140);
  return { verdict, evidence: `Keyword match (${found.join(", ")}): ${snippet}` };
}
