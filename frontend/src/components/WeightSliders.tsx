import { useState } from "react";
import { rebalance } from "../lib/candidates";
import type { Weights } from "../types";
import { Alert, Button } from "./ui";

const ROWS: { key: keyof Weights; label: string; hint: string }[] = [
  { key: "must", label: "Must-have requirements", hint: "Share of must-haves met (partial counts half)" },
  { key: "nice", label: "Nice-to-have requirements", hint: "Share of nice-to-haves met" },
  { key: "semantic", label: "Semantic match", hint: "Embedding similarity between the profile and the job" },
];

const toPercents = (w: Weights): [number, number, number] => [Math.round(w.must * 100), Math.round(w.nice * 100), 100 - Math.round(w.must * 100) - Math.round(w.nice * 100)];
const toWeights = (p: [number, number, number]): Weights => ({ must: p[0] / 100, nice: p[1] / 100, semantic: p[2] / 100 });

/**
 * Score weights with a live re-rank (P1). Dragging previews new totals in the table
 * immediately; Save recomputes the stored scores (no LLM calls).
 */
export function WeightSliders({
  saved,
  onPreview,
  onSave,
  blockedReason,
}: {
  saved: Weights;
  onPreview(w: Weights | null): void;
  onSave(w: Weights): Promise<void>;
  blockedReason: string | null;
}) {
  const [percents, setPercents] = useState(() => toPercents(saved));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const savedPercents = toPercents(saved);
  const dirty = percents.some((p, i) => p !== savedPercents[i]);

  function change(i: number, value: number) {
    const next = rebalance(percents, i, value);
    setPercents(next);
    onPreview(toWeights(next));
  }

  function reset(to: [number, number, number]) {
    setPercents(to);
    onPreview(null);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await onSave(toWeights(percents));
      onPreview(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
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
              onChange={(e) => change(i, Number(e.target.value))}
              className="mt-2 w-full accent-indigo-600"
              aria-describedby={`w-hint-${row.key}`}
            />
            <span id={`w-hint-${row.key}`} className="text-xs text-slate-500">
              {row.hint}
            </span>
          </label>
        ))}
      </div>
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500">
          {dirty ? "Previewing: the table is re-ranked with these weights. Save to keep them." : "Weights always add up to 100%."}
        </p>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => reset([50, 20, 30])} disabled={busy}>
            Defaults
          </Button>
          <Button variant="secondary" size="sm" onClick={() => reset(savedPercents)} disabled={!dirty || busy}>
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
