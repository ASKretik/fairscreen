"""Grouped bar chart of the ablation (precision@5, precision@10, nDCG@10 per method) as a static SVG.

No plotting library: the SVG is written directly so it renders on GitHub in light
and dark mode (colors switch with prefers-color-scheme inside the SVG). Palette:
the first three slots of the validated reference categorical palette, checked
for both surfaces. The light aqua sits under 3:1 contrast, so every bar carries a
value label and the README repeats the numbers as a table.
"""

from html import escape

METRICS = [("p@5", "Precision@5"), ("p@10", "Precision@10"), ("ndcg@10", "nDCG@10")]
SERIES = [("semantic", "Semantic only"), ("requirements", "Requirements only"), ("combined", "Combined score")]

W, H = 680, 380
PAD_L, PAD_R, PAD_T, PAD_B = 48, 16, 84, 44
BAR_W, BAR_GAP, GROUP_GAP = 44, 2, 56
RADIUS = 4

STYLE = """
  .surface { fill: transparent; }
  .title { font: 600 15px -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; fill: #1f2328; }
  .sub, .tick, .legend, .value, .cat { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
  .sub { font-size: 12px; fill: #59636e; }
  .tick { font-size: 11px; fill: #59636e; }
  .cat { font-size: 12px; fill: #1f2328; font-weight: 500; }
  .legend { font-size: 12px; fill: #1f2328; }
  .value { font-size: 11px; fill: #59636e; font-variant-numeric: tabular-nums; }
  .grid { stroke: #d1d9e0; stroke-width: 1; }
  .base { stroke: #818b98; stroke-width: 1; }
  .s1 { fill: #2a78d6; } .s2 { fill: #eb6834; } .s3 { fill: #1baf7a; }
  @media (prefers-color-scheme: dark) {
    .title, .cat, .legend { fill: #f0f6fc; }
    .sub, .tick, .value { fill: #9198a1; }
    .grid { stroke: #3d444d; }
    .base { stroke: #656c76; }
    .s1 { fill: #3987e5; } .s2 { fill: #d95926; } .s3 { fill: #199e70; }
  }
"""


def _bar(x: float, y_top: float, y_base: float, width: float, cls: str, title: str) -> str:
    """A bar with 4 px rounded top corners and a square end on the baseline."""
    h = y_base - y_top
    if h <= 0:
        return f'<rect class="{cls}" x="{x:.1f}" y="{y_base - 1:.1f}" width="{width}" height="1"><title>{escape(title)}</title></rect>'
    r = min(RADIUS, h, width / 2)
    d = (f"M{x:.1f},{y_base:.1f} V{y_top + r:.1f} Q{x:.1f},{y_top:.1f} {x + r:.1f},{y_top:.1f} "
         f"H{x + width - r:.1f} Q{x + width:.1f},{y_top:.1f} {x + width:.1f},{y_top + r:.1f} V{y_base:.1f} Z")
    return f'<path class="{cls}" d="{d}"><title>{escape(title)}</title></path>'


def ablation_chart_svg(mean: dict[str, dict[str, float]], subtitle: str) -> str:
    """`mean[series][metric]` -> SVG text. Missing values are drawn as zero."""
    plot_h = H - PAD_T - PAD_B
    group_w = len(SERIES) * BAR_W + (len(SERIES) - 1) * BAR_GAP
    total_w = len(METRICS) * group_w + (len(METRICS) - 1) * GROUP_GAP
    x0 = PAD_L + (W - PAD_L - PAD_R - total_w) / 2
    y_base = PAD_T + plot_h

    def y(v: float) -> float:
        return y_base - max(0.0, min(1.0, v)) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
        f'aria-labelledby="t d">',
        f"<style>{STYLE}</style>",
        '<title id="t">Ranking quality by method</title>',
        f'<desc id="d">{escape(subtitle)}. '
        + "; ".join(f"{label}: " + ", ".join(f"{m} {mean.get(key, {}).get(mk, 0):.2f}" for mk, m in METRICS)
                    for key, label in SERIES)
        + "</desc>",
        f'<rect class="surface" width="{W}" height="{H}"/>',
        f'<text class="title" x="{PAD_L - 32}" y="24">Ranking quality by method</text>',
        f'<text class="sub" x="{PAD_L - 32}" y="42">{escape(subtitle)}</text>',
    ]
    # legend, one row above the plot
    lx = PAD_L - 32
    for i, (_, label) in enumerate(SERIES):
        parts.append(f'<rect class="s{i + 1}" x="{lx}" y="56" width="12" height="12" rx="3"/>')
        parts.append(f'<text class="legend" x="{lx + 18}" y="66">{escape(label)}</text>')
        lx += 18 + len(label) * 7 + 24
    # recessive grid and y ticks
    for t in (0.25, 0.5, 0.75, 1.0):
        parts.append(f'<line class="grid" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>')
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        parts.append(f'<text class="tick" x="{PAD_L - 8}" y="{y(t) + 4:.1f}" text-anchor="end">{t:.2f}</text>')
    # bars, value labels and category labels
    for g, (mk, mlabel) in enumerate(METRICS):
        gx = x0 + g * (group_w + GROUP_GAP)
        for i, (key, label) in enumerate(SERIES):
            v = mean.get(key, {}).get(mk, 0.0)
            bx = gx + i * (BAR_W + BAR_GAP)
            parts.append(_bar(bx, y(v), y_base, BAR_W, f"s{i + 1}", f"{label}, {mlabel}: {v:.2f}"))
            parts.append(f'<text class="value" x="{bx + BAR_W / 2:.1f}" y="{y(v) - 6:.1f}" text-anchor="middle">{v:.2f}</text>')
        parts.append(f'<text class="cat" x="{gx + group_w / 2:.1f}" y="{y_base + 22}" text-anchor="middle">{mlabel}</text>')
    parts.append(f'<line class="base" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y_base}" y2="{y_base}"/>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
