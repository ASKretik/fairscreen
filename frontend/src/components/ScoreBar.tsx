/** Horizontal bar for a 0–100 score or a 0–1 fraction. */
export function ScoreBar({
  value,
  max = 100,
  label,
  className = "",
}: {
  value: number;
  max?: number;
  label?: string;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const color = pct >= 70 ? "bg-emerald-500" : pct >= 45 ? "bg-indigo-500" : "bg-slate-400";
  return (
    <div className={`h-2 w-full overflow-hidden rounded-full bg-slate-100 ${className}`} role="meter" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}
