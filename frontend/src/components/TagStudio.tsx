import { useState, type FormEvent } from "react";
import { DEFAULT_TAG_WEIGHT, tagShares } from "../lib/candidates";
import {
  labelName,
  MAX_TAGS_PER_GROUP,
  roleSetup,
  setupRequirements,
  topLabels,
  type ActiveTag,
  type DemoPool,
  type DemoSetup,
} from "../lib/demoPool";
import type { Candidate } from "../types";
import { Icon } from "./icons";
import { Button, Card } from "./ui";
import { GroupWeightSliders, sharePercent, TagWeightPicker } from "./WeightSliders";

type Group = "must" | "nice";
const GROUP_TITLES: Record<Group, string> = { must: "Must-have tags", nice: "Nice-to-have tags" };
const TOP_N = 10;

let customId = 0;

function TagRow({
  tag,
  share,
  group,
  canMove,
  onWeight,
  onMove,
  onRemove,
}: {
  tag: ActiveTag;
  share: number | undefined;
  group: Group;
  canMove: boolean;
  onWeight(w: number): void;
  onMove(): void;
  onRemove(): void;
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 py-2.5">
      <div className="min-w-0 flex-1 basis-48">
        <p className="text-sm text-slate-900">{tag.text}</p>
        {tag.custom && (
          <p className="mt-0.5 text-[11px] text-amber-700" title="Typed in here: matched by keywords in your browser, not judged by AI.">
            Your tag · approximate keyword match
          </p>
        )}
      </div>
      <span className="w-10 text-right text-xs text-slate-500 tabular-nums" title="Share of the total score">
        {sharePercent(share)}
      </span>
      <TagWeightPicker value={tag.weight} onChange={onWeight} label={tag.text} />
      <div className="flex">
        <button
          type="button"
          onClick={onMove}
          disabled={!canMove}
          title={group === "must" ? "Move to nice-to-have" : "Move to must-have"}
          aria-label={`${tag.text}: ${group === "must" ? "move to nice-to-have" : "move to must-have"}`}
          className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30"
        >
          <Icon name="arrowRight" className={`size-4 ${group === "must" ? "rotate-90 lg:rotate-0" : "-rotate-90 lg:rotate-180"}`} />
        </button>
        <button
          type="button"
          onClick={onRemove}
          title="Remove tag"
          aria-label={`Remove ${tag.text}`}
          className="rounded-md p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-700"
        >
          <Icon name="x" className="size-4" />
        </button>
      </div>
    </li>
  );
}

function SelectionSummary({ candidates, category }: { candidates: Candidate[]; category?: string }) {
  const top = topLabels(candidates, TOP_N);
  const own = top.find((t) => t.label === category)?.count ?? 0;
  const n = Math.min(TOP_N, candidates.length);
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Who makes the top {n}?</h3>
        {category && candidates.some((c) => c.label === category) && (
          <p className="text-xs text-slate-500">
            {own} of {n} are {labelName(category)} resumes, the role's own dataset category.
          </p>
        )}
      </div>
      <div className="mt-2 flex h-3 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
        {top.map((t, i) => (
          <div
            key={t.label}
            className={`${t.label === category ? "bg-indigo-600" : i % 2 ? "bg-slate-300" : "bg-slate-400"} border-r-2 border-white last:border-r-0`}
            style={{ width: `${(t.count / n) * 100}%` }}
          />
        ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-1.5" aria-label={`Dataset categories in the top ${n}`}>
        {top.map((t) => (
          <li
            key={t.label}
            className={`rounded-md px-2 py-0.5 text-xs ${t.label === category ? "bg-indigo-50 font-medium text-indigo-800" : "bg-slate-100 text-slate-700"}`}
          >
            {labelName(t.label)} <span className="tabular-nums">{t.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The demo's screening setup: a role preset, the active tags with their weights, tags to add
 * (from the AI-judged library, or typed in and keyword-matched) and the group weights.
 */
export function TagStudio({
  pool,
  setup,
  candidates,
  onChange,
  onRoleChange,
}: {
  pool: DemoPool;
  setup: DemoSetup;
  candidates: Candidate[];
  onChange(s: DemoSetup): void;
  onRoleChange(roleId: string): void;
}) {
  const [addTo, setAddTo] = useState<Group>("nice");
  const [custom, setCustom] = useState("");
  const role = pool.roles.find((r) => r.id === setup.roleId) ?? pool.roles[0];
  const shares = tagShares(setupRequirements(pool, setup), setup.weights);
  const active = new Set([...setup.must, ...setup.nice].map((t) => t.id));
  const full = (g: Group) => setup[g].length >= MAX_TAGS_PER_GROUP;
  const other = (g: Group): Group => (g === "must" ? "nice" : "must");

  const update = (g: Group, tags: ActiveTag[]) => onChange({ ...setup, [g]: tags });
  const add = (tag: ActiveTag) => !full(addTo) && update(addTo, [...setup[addTo], tag]);
  const move = (g: Group, id: string) => {
    const tag = setup[g].find((t) => t.id === id)!;
    onChange({ ...setup, [g]: setup[g].filter((t) => t.id !== id), [other(g)]: [...setup[other(g)], tag] });
  };

  function addCustom(e: FormEvent) {
    e.preventDefault();
    const text = custom.trim();
    if (!text || full(addTo)) return;
    add({ id: `k${++customId}`, text, kind: "skill", weight: DEFAULT_TAG_WEIGHT, custom: true });
    setCustom("");
  }

  const groups = [role.id, ...pool.roles.map((r) => r.id).filter((id) => id !== role.id), "general"];
  const groupName = (g: string) => (g === "general" ? "General" : (pool.roles.find((r) => r.id === g)?.title ?? g));

  return (
    <Card className="divide-y divide-slate-100">
      <div className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">1. Pick a role</h2>
          <p className="mt-0.5 text-xs text-slate-500">Loads that role's default tags. You can change everything after.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {pool.roles.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => onRoleChange(r.id)}
              aria-pressed={r.id === role.id}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ring-1 ring-inset transition-colors ${
                r.id === role.id ? "bg-slate-900 text-white ring-slate-900" : "bg-white text-slate-700 ring-slate-300 hover:bg-slate-50"
              }`}
            >
              {r.title}
            </button>
          ))}
        </div>
      </div>

      <div className="p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-900">2. Tune the tags</h2>
          <button type="button" onClick={() => onChange(roleSetup(pool, role.id))} className="text-xs font-medium text-indigo-600 hover:text-indigo-800">
            Reset to the role's defaults
          </button>
        </div>
        <p className="mt-0.5 text-xs text-slate-500">
          1–5 sets a tag's weight within its group (3 is normal). The percentage is the tag's share of the score.
        </p>
        <div className="mt-4 grid gap-6 lg:grid-cols-2">
          {(["must", "nice"] as const).map((g) => (
            <div key={g}>
              <h3 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
                {GROUP_TITLES[g]} <span className="font-normal normal-case">({setup[g].length}/{MAX_TAGS_PER_GROUP})</span>
              </h3>
              {setup[g].length === 0 ? (
                <p className="mt-3 rounded-lg border border-dashed border-slate-300 px-3 py-4 text-center text-xs text-slate-500">
                  No {g === "must" ? "must-have" : "nice-to-have"} tags. Add some below.
                </p>
              ) : (
                <ul className="mt-1 divide-y divide-slate-100">
                  {setup[g].map((t) => (
                    <TagRow
                      key={t.id}
                      tag={t}
                      group={g}
                      share={shares.get(t.id)}
                      canMove={!full(other(g))}
                      onWeight={(weight) => update(g, setup[g].map((x) => (x.id === t.id ? { ...x, weight } : x)))}
                      onMove={() => move(g, t.id)}
                      onRemove={() => update(g, setup[g].filter((x) => x.id !== t.id))}
                    />
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>

        <div className="mt-6 rounded-xl bg-slate-50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-slate-900">Add tags</h3>
            <div className="inline-flex items-center gap-2 text-xs text-slate-600">
              Add to
              <div className="inline-flex rounded-lg bg-white p-0.5 ring-1 ring-slate-200" role="radiogroup" aria-label="Add new tags to">
                {(["must", "nice"] as const).map((g) => (
                  <button
                    key={g}
                    type="button"
                    role="radio"
                    aria-checked={addTo === g}
                    onClick={() => setAddTo(g)}
                    className={`rounded-md px-2.5 py-1 font-medium ${addTo === g ? "bg-indigo-600 text-white" : "text-slate-600 hover:text-slate-900"}`}
                  >
                    {g === "must" ? "Must-have" : "Nice-to-have"}
                  </button>
                ))}
              </div>
            </div>
          </div>
          {full(addTo) && (
            <p className="mt-2 text-xs text-amber-800">
              {GROUP_TITLES[addTo]} are full ({MAX_TAGS_PER_GROUP}). Remove one, or add to the other group.
            </p>
          )}
          <form onSubmit={addCustom} className="mt-3 flex flex-col gap-2 sm:flex-row">
            <input
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              maxLength={120}
              placeholder="Type your own tag, e.g. Kubernetes or payroll"
              aria-label="Your own tag"
              className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 focus:outline-none"
            />
            <Button type="submit" variant="secondary" disabled={!custom.trim() || full(addTo)}>
              Add tag
            </Button>
          </form>
          <p className="mt-1.5 text-[11px] text-slate-500">
            Library tags below were judged by AI for every resume in advance. Tags you type are matched by keywords in your
            browser, so they're approximate.
          </p>
          <div className="mt-4 space-y-3">
            {groups.map((g) => {
              const tags = pool.tags.filter((t) => t.group === g && !active.has(t.id));
              if (tags.length === 0) return null;
              return (
                <div key={g}>
                  <p className="text-[11px] font-semibold tracking-wide text-slate-500 uppercase">{groupName(g)}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {tags.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        disabled={full(addTo)}
                        onClick={() => add({ id: t.id, text: t.text, kind: t.kind, weight: DEFAULT_TAG_WEIGHT, custom: false })}
                        className="rounded-full bg-white px-2.5 py-1 text-xs text-slate-700 ring-1 ring-slate-200 ring-inset hover:text-indigo-700 hover:ring-indigo-300 disabled:opacity-40"
                      >
                        + {t.text}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="p-6">
        <h2 className="text-sm font-semibold text-slate-900">3. Balance the score</h2>
        <div className="mt-4">
          <GroupWeightSliders
            weights={setup.weights}
            onChange={(weights) => onChange({ ...setup, weights })}
            semanticHint={`Similarity of each resume to the ${role.title} tags (precomputed)`}
          />
        </div>
      </div>

      <div className="p-6">
        <SelectionSummary candidates={candidates} category={role.category} />
      </div>
    </Card>
  );
}
