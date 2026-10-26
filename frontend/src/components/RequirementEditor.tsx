import { DEFAULT_TAG_WEIGHT, tagWeight } from "../lib/candidates";
import type { JobRequirements, ReqKind, Requirement } from "../types";
import { Button } from "./ui";
import { TagWeightPicker } from "./WeightSliders";

const KINDS: ReqKind[] = ["skill", "experience", "education", "certification", "other"];
export const MAX_MUST = 8;
export const MAX_NICE = 8;

let tempId = 0;
export const newRequirement = (prefix: string): Requirement => ({
  id: `${prefix}-new-${++tempId}`,
  text: "",
  kind: "skill",
  weight: DEFAULT_TAG_WEIGHT,
});

function RequirementList({
  title,
  hint,
  items,
  max,
  prefix,
  onChange,
}: {
  title: string;
  hint: string;
  items: Requirement[];
  max: number;
  prefix: string;
  onChange(items: Requirement[]): void;
}) {
  const update = (i: number, patch: Partial<Requirement>) =>
    onChange(items.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <fieldset>
      <legend className="text-sm font-semibold text-slate-900">{title}</legend>
      <p className="mt-0.5 text-xs text-slate-500">{hint}</p>
      <ul className="mt-3 space-y-2">
        {items.map((r, i) => (
          <li key={r.id} className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              value={r.text}
              onChange={(e) => update(i, { text: e.target.value })}
              maxLength={300}
              placeholder="e.g. 3+ years of Python in production"
              aria-label={`${title} ${i + 1}`}
              className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 focus:outline-none"
            />
            <div className="flex flex-wrap items-center gap-2">
              <TagWeightPicker value={tagWeight(r)} onChange={(weight) => update(i, { weight })} label={r.text || `${title} ${i + 1}`} />
              <select
                value={r.kind}
                onChange={(e) => update(i, { kind: e.target.value as ReqKind })}
                aria-label="Tag type"
                className="rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
              <Button variant="ghost" size="sm" onClick={() => onChange(items.filter((_, j) => j !== i))} aria-label="Remove tag">
                Remove
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <Button
        variant="secondary"
        size="sm"
        className="mt-3"
        disabled={items.length >= max}
        onClick={() => onChange([...items, newRequirement(prefix)])}
      >
        + Add tag {items.length >= max ? `(max ${max})` : ""}
      </Button>
    </fieldset>
  );
}

/** Returns an error message, or null if the requirements can be saved. */
export function validateRequirements(req: JobRequirements): string | null {
  const must = req.must_have.filter((r) => r.text.trim());
  const nice = req.nice_to_have.filter((r) => r.text.trim());
  if (!req.role_title.trim()) return "Add a role title.";
  if (must.length < 1) return "Add at least one must-have tag.";
  if (must.length > MAX_MUST || nice.length > MAX_NICE) return `Use at most ${MAX_MUST} must-haves and ${MAX_NICE} nice-to-haves.`;
  return null;
}

export function RequirementEditor({ value, onChange }: { value: JobRequirements; onChange(v: JobRequirements): void }) {
  return (
    <div className="space-y-6">
      <label className="block">
        <span className="text-sm font-semibold text-slate-900">Role title</span>
        <input
          value={value.role_title}
          onChange={(e) => onChange({ ...value, role_title: e.target.value })}
          className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 focus:outline-none"
        />
      </label>
      <RequirementList
        title="Must-have tags"
        hint="Each tag is checked against every resume. Missing one shows a badge but never auto-rejects. The 1–5 buttons set the tag's weight within its group (3 is normal)."
        items={value.must_have}
        max={MAX_MUST}
        prefix="m"
        onChange={(must_have) => onChange({ ...value, must_have })}
      />
      <RequirementList
        title="Nice-to-have tags"
        hint="Count for less in the score overall; weights work the same way."
        items={value.nice_to_have}
        max={MAX_NICE}
        prefix="n"
        onChange={(nice_to_have) => onChange({ ...value, nice_to_have })}
      />
    </div>
  );
}
