import type { Candidate } from "../types";
import { coverage, primaryEducation, rankMap } from "./candidates";

const HEADER = [
  "Rank",
  "Anon ID",
  "Status",
  "Score",
  "Must-have coverage",
  "Nice-to-have coverage",
  "Semantic match",
  "Must-haves met",
  "Missing must-have",
  "Institution",
  "Degree",
  "Name",
  "Email",
  "File name",
];

function cell(value: string | number | null | undefined): string {
  const s = value === null || value === undefined ? "" : String(value);
  // Quote everything, and defuse spreadsheet formulas (=, +, -, @ at the start).
  const safe = /^[=+\-@]/.test(s) ? `'${s}` : s;
  return `"${safe.replace(/"/g, '""')}"`;
}

const pct = (x: number | undefined) => (x === undefined ? "" : (x * 100).toFixed(0));

/**
 * One row per candidate, in the given order. Name, email and file name are filled
 * in only for revealed candidates (SPEC §9, §6.2).
 */
export function candidatesToCsv(rows: Candidate[], all: Candidate[] = rows): string {
  const ranks = rankMap(all);
  const lines = [HEADER.map(cell).join(",")];
  for (const c of rows) {
    const cov = coverage(c.evaluation?.must_have);
    const edu = primaryEducation(c);
    const revealed = c.revealed;
    lines.push(
      [
        ranks.get(c.id) ?? "",
        c.anonId,
        c.status,
        c.score ? c.score.total.toFixed(1) : "",
        pct(c.score?.must_have),
        pct(c.score?.nice_to_have),
        pct(c.score?.semantic),
        c.evaluation ? `${cov.met}/${cov.total}` : "",
        c.score ? (c.score.missing_must_have ? "yes" : "no") : "",
        edu?.institution,
        [edu?.degree, edu?.field].filter(Boolean).join(", "),
        revealed ? revealed.name : "",
        revealed ? revealed.email : "",
        revealed ? c.fileName : "",
      ]
        .map(cell)
        .join(","),
    );
  }
  return lines.join("\r\n") + "\r\n";
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function csvFileName(jobTitle: string, date = new Date()): string {
  const slug = jobTitle.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "job";
  return `fairscreen-${slug}-${date.toISOString().slice(0, 10)}.csv`;
}
