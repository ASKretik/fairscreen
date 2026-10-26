import { useState } from "react";
import { DEFAULT_TAG_WEIGHT, rebalance, TAG_WEIGHTS, tagShares, tagWeight } from "../lib/candidates";
import type { JobRequirements, Requirement, Weights } from "../types";
import { Alert, Button } from "./ui";

const ROWS: { key: keyof Weights; label: string; hint: string }[] = [
  { key: "must", label: "Must-have tags", hint: "Weighted share of must-have tags met (partial counts half)" },
  { key: "nice", label: "Nice-to-have tags", hint: "Weighted share of nice-to-have tags met" },
  { key: "semantic", label: "Semantic match", hint: "Embedding similarity between the profile and the job" },
];

export const DEFAULT_WEIGHTS: Weights = { must: 0.5, nice: 0.2, semantic: 0.3 };

const toPercents = (w: Weights): [number, number, number] => [Math.round(w.must * 100), Math.round(w.nice * 100), 100 - Math.round(w.must * 100) - Math.round(w.nice * 100)];
const toWeights = (p: [number, number, number]): Weights => ({ must: p[0] / 100, nice: p[1] / 100, semantic: p[2] / 100 });

const WEIGHT_NAMES: Record<number, string> = { 1: "low", 2: "below normal", 3: "normal", 4: "high", 5: "critical" };

/** A tag's weight within its group, 1 (low) to 5 (critical); 3 is normal. */
export function TagWeightPicker({ value, onChange, label }: { value: number; onChange(v: number): void; label: string }) {
  return (
    <div className="inline-flex shrink-0 rounded-lg bg-slate-100 p-0.5" role="radiogroup" aria-label={`Weight for ${label}`}>
      {TAG_WEIGHTS.map((w) => (
        <button
          key={w}
          type="button"
          role="radio"
          aria-checked={value === w}
          title={`Weight ${w}: ${WEIGHT_NAMES[w]}`}
          onClick={() => onChange(w)}
          className={`size-7 rounded-md text-xs font-semibold tabular-nums transition-colors ${
            value === w ? "bg-indigo-600 text-white shadow-sm" : "text-slate-500 hover:bg-white hover:text-slate-900"
          }`}
        >
          {w}
        </button>
      ))}
    </div>
  );
}

/** Must-have / nice-to-have / semantic sliders that always add up to 100%. */
export function GroupWeightSliders({ weights, onChange, semanticHint }: { weights: Weights; onChange(w: Weights): void; semanticHint?: string }) {
  const percents = toPercents(weights);
  return (
    <div className="grid gap-5 md:grid-cols-3">
      {ROWS.map((row, i) => (
        <label key={row.key} className="block">
          <span className="flex items-baseline justify-between text-sm">
            <span className="font-medium text-slate-800">{row.label}</span>
            <span className="font-semibold text-slate-900 tabular-nums">{percents[i]}%</span>
          </span>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={percents[i]}
            onChange={(e) => onChange(toWeights(rebalance(percents, i, Number(e.target.value))))}
            className="mt-2 w-full accent-indigo-600"
            aria-describedby={`w-hint-${row.key}`}
          />
          <span id={`w-hint-${row.key}`} className="text-xs text-slate-500">
            {row.key === "semantic" && semanticHint ? semanticHint : row.hint}
          </span>
        </label>
      ))}
    </div>
  );
}

export function sharePercent(share: number | undefined): string {
  const p = (share ?? 0) * 100;
  return p > 0 && p < 1 ? "<1%" : `${Math.round(p)}%`;
}

function TagWeightList({
  title,
  items,
  shares,
  onChange,
}: {
  title: string;
  items: Requirement[];
  shares: Map<string, number>;
  onChange(id: string, weight: number): void;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">{title}</h4>
      <ul className="mt-2 divide-y divide-slate-100">
        {items.map((r) => (
          <li key={r.id} className="flex items-center gap-3 py-2">
            <span className="min-w-0 flex-1 text-sm text-slate-800">{r.text}</span>
            <span className="w-12 text-right text-xs text-slate-500 tabular-nums" title="Share of the total score">
              {sharePercent(shares.get(r.id))}
            </span>
            <TagWeightPicker value={tagWeight(r)} onChange={(w) => onChange(r.id, w)} label={r.text} />
          </li>
        ))}
      </ul>
    </div>
  );
}

const withWeights = (req: JobRequirements, tw: Record<string, number>): JobRequirements => ({
  ...req,
  must_have: req.must_have.map((r) => ({ ...r, weight: tw[r.id] ?? tagWeight(r) })),
  nice_to_have: req.nice_to_have.map((r) => ({ ...r, weight: tw[r.id] ?? tagWeight(r) })),
});

const savedTagWeights = (req: JobRequirements): Record<string, number> =>
  Object.fromEntries([...req.must_have, ...req.nice_to_have].map((r) => [r.id, tagWeight(r)]));

/**
 * Group and tag weights with a live re-rank (P1). Changes preview new scores in the table
 * immediately; Save recomputes the stored scores from each checklist (no LLM calls).
 */
export function WeightSliders({
  saved,
  requirements,
  onPreview,
  onSave,
  blockedReason,
}: {
  saved: Weights;
  requirements: JobRequirements;
  onPreview(p: { weights: Weights; requirements: JobRequirements } | null): void;
  onSave(w: Weights, tagWeights: Record<string, number>): Promise<void>;
  blockedReason: string | null;
}) {
  const [weights, setWeights] = useState(saved);
  const [tags, setTags] = useState(() => savedTagWeights(requirements));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const savedTags = savedTagWeights(requirements);
  const dirty =
    toPercents(weights).some((p, i) => p !== toPercents(saved)[i]) || Object.entries(tags).some(([id, w]) => savedTags[id] !== w);
  const preview = withWeights(requirements, tags);
  const shares = tagShares(preview, weights);

  function update(w: Weights, tw: Record<string, number>) {
    setWeights(w);
    setTags(tw);
    onPreview({ weights: w, requirements: withWeights(requirements, tw) });
  }

  function reset(w: Weights, tw: Record<string, number>) {
    setWeights(w);
    setTags(tw);
    onPreview(null);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await onSave(weights, tags);
      onPreview(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const defaults = Object.fromEntries(Object.keys(tags).map((id) => [id, DEFAULT_TAG_WEIGHT]));
  return (
    <div className="space-y-6">
      <GroupWeightSliders weights={weights} onChange={(w) => update(w, tags)} />
      <div className="grid gap-6 lg:grid-cols-2">
        <TagWeightList title="Must-have tags" items={preview.must_have} shares={shares} onChange={(id, w) => update(weights, { ...tags, [id]: w })} />
        <TagWeightList title="Nice-to-have tags" items={preview.nice_to_have} shares={shares} onChange={(id, w) => update(weights, { ...tags, [id]: w })} />
      </div>
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500">
          {dirty
            ? "Previewing: the table is re-ranked with these weights. Save to keep them."
            : "Tag weights run from 1 (low) to 5 (critical) within their group; the percentages show each tag's share of the score."}
        </p>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => update(DEFAULT_WEIGHTS, defaults)} disabled={busy}>
            Defaults
          </Button>
          <Button variant="secondary" size="sm" onClick={() => reset(saved, savedTags)} disabled={!dirty || busy}>
            Cancel
          </Button>
          <span title={blockedReason ?? undefined}>
            <Button size="sm" onClick={save} loading={busy} disabled={!dirty || Boolean(blockedReason)}>
              Save weights
            </Button>
          </span>
        </div>
      </div>
    </div>
  );
}
