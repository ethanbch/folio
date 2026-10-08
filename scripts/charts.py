"""Draws the README charts as SVG, light and dark, from the measurements in docs/EVAL.md.

Usage: python3 scripts/charts.py   (writes docs/charts/*.svg)

Colours are Readout tokens (tokens/readout.json in the Readout repository): page and surface,
ink, ink-secondary, ink-muted, border, series-1 and ramp-3/ramp-4 for earlier stages.
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "charts"

THEMES = {
    "light": {"bg": "#ffffff", "ink": "#1b1c1d", "ink2": "#504f4a", "muted": "#6e6d67", "rule": "#e6e5e1",
              "bar": "#5b62e0", "bar_dim": "#b9beff"},
    "dark": {"bg": "#191a1c", "ink": "#ecebe7", "ink2": "#b0afa9", "muted": "#8a8982", "rule": "#2a2b2e",
             "bar": "#747cf0", "bar_dim": "#3a3e85"},
}
FONT = "IBM Plex Sans, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
MONO = "JetBrains Mono, SF Mono, Menlo, monospace"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def bars(name: str, title: str, subtitle: str, rows: list[tuple[str, str, float, str]], vmax: float, note: str = "",
         highlight_last: bool = True) -> None:
    """Horizontal bars. rows: (label, caption, value, value text). With highlight_last, the last row is the story."""
    width, label_w, left, right = 760, 250, 24, 90
    top, row_h, bar_h = 92, 44, 20
    height = top + row_h * len(rows) + (48 if note else 24)
    track = width - left - label_w - right
    for theme, c in THEMES.items():
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
               f'<rect width="{width}" height="{height}" rx="16" fill="{c["bg"]}"/>',
               f'<text x="{left}" y="40" font-family="{FONT}" font-size="17" font-weight="600" fill="{c["ink"]}">{esc(title)}</text>',
               f'<text x="{left}" y="64" font-family="{FONT}" font-size="13" fill="{c["ink2"]}">{esc(subtitle)}</text>']
        for i, (label, caption, value, text) in enumerate(rows):
            y = top + i * row_h
            last = highlight_last and i == len(rows) - 1
            plain = not highlight_last
            cy = y + bar_h / 2
            out.append(f'<text x="{left}" y="{cy + (-1 if caption else 5)}" font-family="{FONT}" font-size="14" '
                       f'font-weight="{600 if last else 400}" fill="{c["ink"]}">{esc(label)}</text>')
            if caption:
                out.append(f'<text x="{left}" y="{cy + 15}" font-family="{FONT}" font-size="11.5" fill="{c["muted"]}">{esc(caption)}</text>')
            w = max(4.0, track * value / vmax)
            x0 = left + label_w
            r = 4  # rounded data end, square at the baseline
            path = f"M{x0},{y} H{x0 + w - r} Q{x0 + w},{y} {x0 + w},{y + r} V{y + bar_h - r} Q{x0 + w},{y + bar_h} {x0 + w - r},{y + bar_h} H{x0} Z"
            out.append(f'<path d="{path}" fill="{c["bar"] if last or plain else c["bar_dim"]}"/>')
            out.append(f'<text x="{x0 + w + 10}" y="{cy + 5}" font-family="{MONO}" font-size="13" '
                       f'font-weight="{600 if last else 400}" fill="{c["ink"] if last or plain else c["ink2"]}">{esc(text)}</text>')
        out.append(f'<line x1="{left + label_w}" y1="{top - 8}" x2="{left + label_w}" y2="{top + row_h * len(rows) - 16}" stroke="{c["rule"]}" stroke-width="1"/>')
        if note:
            out.append(f'<text x="{left}" y="{height - 22}" font-family="{FONT}" font-size="11.5" fill="{c["muted"]}">{esc(note)}</text>')
        out.append("</svg>")
        (OUT / f"{name}-{theme}.svg").write_text("\n".join(out) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bars(
        "quality",
        "Each stage puts the right file higher",
        "Mean reciprocal rank on 61 real queries (1.0 = the expected file always comes first)",
        [
            ("Keywords in names", "file and folder names only", 0.661, "0.661"),
            ("+ file content", "PDF, Office, text, code", 0.687, "0.687"),
            ("+ meaning", "multilingual embeddings, fused", 0.724, "0.724"),
            ("+ dates and types", "« le pdf de la semaine dernière »", 0.736, "0.736"),
            ("+ ranking signals", "recency, history, exact names", 0.755, "0.755"),
            ("folio 0.1.0", "+ cross-encoder · 84 % in the top 3", 0.783, "0.783"),
        ],
        vmax=0.95,
        note="M3 MacBook Air, 4 408 files. Method and every variant tested: docs/EVAL.md",
    )
    bars(
        "speed",
        "Ready in seconds",
        "Seconds, measured on an M3 MacBook Air (8 GB)",
        [
            ("Open the page", "npx folio-search, installed", 0.9, "0.9 s"),
            ("Search by name, first run", "4 408 files walked and indexed", 1.2, "1.2 s"),
            ("A changed file is found", "FSEvents, debounced", 2.5, "2.5 s"),
            ("Install from scratch", "npx, empty cache, Python included", 4.2, "4.2 s"),
        ],
        vmax=5.0,
        note="Full first index, content and vectors: 6 min 4 s at low priority. Search works from the first second.",
        highlight_last=False,
    )
    print(f"Wrote {len(list(OUT.glob('*.svg')))} charts in {OUT}")


if __name__ == "__main__":
    main()
