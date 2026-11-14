#!/usr/bin/env python3
"""Build preview.html: flowerized faces next to the originals, with live sliders."""
import argparse
import html
import re
from pathlib import Path

import flowerize as F

ap = argparse.ArgumentParser()
ap.add_argument("--subset", action="store_true", help="only the built-in sample")
ap.add_argument("--out", type=Path, default=F.HERE / "preview.html")
ap.add_argument("--custom", type=Path, default=F.HERE / "custom",
                help="hand-edited finished SVGs; used in place of the generated version when present")
args = ap.parse_args()

flower = F.Flower(F.DEFAULT_FLOWER)
names = list(F.SUBSET if args.subset else F.face_names())
custom = {p.stem: p for p in sorted(args.custom.glob("*.svg"))} if args.custom.is_dir() else {}
if not args.subset:
    names += [n for n in custom if n not in names]  # hand-made extras not in the face list

_n = 0


def uniq_ids(svg):
    """Prefix ids (clipPaths etc) so inlined SVGs can't steal each other's defs."""
    global _n
    _n += 1
    p = f"e{_n}-"
    svg = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{p}{m.group(1)}"', svg)
    svg = re.sub(r'url\(#([^)]+)\)', lambda m: f'url(#{p}{m.group(1)})', svg)
    return re.sub(r'href="#([^"]+)"', lambda m: f'href="#{p}{m.group(1)}"', svg)


def strip_prolog(svg):
    """Drop the XML declaration / DOCTYPE that editors add, so the SVG can be inlined."""
    return svg[svg.index("<svg"):]


def flower_svg(name):
    """(svg markup, is_custom) - the hand-edited file if there is one, else generated."""
    if name in custom:
        return uniq_ids(strip_prolog(custom[name].read_text(encoding="utf-8"))), True
    f = F.DEFAULT_SRC / f"{name}.svg"
    out = F.process_file(f, flower, tag=True) if f.exists() else None
    return (uniq_ids(out) if out else None), False


tiles = []
n_custom = 0
for name in names:
    f = F.DEFAULT_SRC / f"{name}.svg"
    out, is_custom = flower_svg(name)
    if out is None:
        continue
    n_custom += is_custom
    src = uniq_ids(f.read_text(encoding="utf-8")) if f.exists() else ""
    char = "".join(chr(int(p, 16)) for p in f.stem.split("-"))
    tiles.append(
        f'<figure class="tile"><div class="pair">'
        f'<div class="orig" aria-label="original">{src}</div>'
        f'<div class="new">{out}</div></div>'
        f'<figcaption><span class="ch">{html.escape(char)}</span>'
        f'<code>{name}</code>'
        + ('<span class="badge" title="Hand-edited version from custom/">edited</span>' if is_custom else '')
        + '</figcaption></figure>'
    )

sample = {}
for code in ["1f60a", "1f602", "1f60d", "1f914", "1f973", "1f62d", "1f621"]:
    sample[code] = flower_svg(code)[0].replace("<svg ", '<svg class="inl" ', 1)

page = f"""<title>Flower Faces</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400&display=swap">
<style>
/* Layout: a quiet control bar over a dense specimen grid of tiles, one emoji per tile. */
:root {{
  --bg: #f6f5f3; --surface: #ffffff; --fg: #1f1d1b; --muted: #6f6a64; --line: #e4e0db;
  --accent: #c4623f;
  --display: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif;
  --body: "Inter", "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #161514; --surface: #201e1c; --fg: #efebe6; --muted: #a29c95; --line: #34302d; --accent: #e3896a; color-scheme: dark }} }}
:root[data-theme="dark"] {{
  --bg: #161514; --surface: #201e1c; --fg: #efebe6; --muted: #a29c95; --line: #34302d; --accent: #e3896a; color-scheme: dark }}
body {{ background: var(--bg); color: var(--fg); font-family: var(--body); font-size: 15px; line-height: 1.5; }}
.wrap {{ max-width: 1120px; margin: 0 auto; padding-block: 40px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 28px; }}
h1 {{ font-family: var(--display); font-weight: 700; font-size: clamp(32px, 5vw, 48px); line-height: 1.05; margin: 0; letter-spacing: -0.02em; text-wrap: balance; }}
.lede {{ color: var(--muted); max-width: 62ch; margin: 8px 0 0; }}
.lede b {{ color: var(--fg); font-weight: 500; }}
.controls {{ display: flex; flex-wrap: wrap; gap: 16px 32px; align-items: center;
  padding: 16px 20px; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }}
.ctl {{ display: grid; gap: 4px; min-width: 0; }}
.ctl label {{ font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); display: flex; justify-content: space-between; gap: 12px; }}
.ctl output {{ font-family: var(--mono); color: var(--fg); letter-spacing: 0; text-transform: none; font-variant-numeric: tabular-nums; }}
input[type=range] {{ width: 200px; max-width: 100%; accent-color: var(--accent); }}
.swatches {{ display: flex; gap: 6px; align-items: center; }}
input[type=color] {{ width: 32px; height: 24px; padding: 0; border: 1px solid var(--line); border-radius: 4px; background: none; cursor: pointer; }}
.sw {{ width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--surface); outline: 1px solid var(--line); background: var(--c); cursor: pointer; padding: 0; }}
.sw:focus-visible, input:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
.toggle {{ display: flex; gap: 8px; align-items: center; cursor: pointer; font-size: 14px; }}
.toggle input {{ accent-color: var(--accent); width: 16px; height: 16px; }}
.inline-demo {{ font-size: 17px; margin: 0; color: var(--fg); }}
.inline-demo .inl {{ width: 1.25em; height: 1.25em; vertical-align: -0.25em; margin: 0 1px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 10px; }}
.tile {{ margin: 0; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 14px 8px 10px; display: grid; gap: 8px; justify-items: center; }}
.pair {{ display: flex; gap: 6px; align-items: center; justify-content: center; }}
.pair svg {{ display: block; width: 72px; height: 72px; }}
.orig {{ display: none; }}
.compare .orig {{ display: block; }}
.compare .pair svg {{ width: 48px; height: 48px; }}
.compare .grid {{ grid-template-columns: repeat(auto-fill, minmax(128px, 1fr)); }}
figcaption {{ display: flex; gap: 6px; align-items: baseline; font-size: 12px; color: var(--muted); }}
figcaption code {{ font-family: var(--mono); font-size: 11px; }}
.ch {{ font-size: 14px; }}
.badge {{ font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--accent); border: 1px solid currentColor; border-radius: 999px; padding: 0 6px; line-height: 16px; }}
figcaption {{ flex-wrap: wrap; justify-content: center; }}
.count {{ font-size: 13px; color: var(--muted); margin: 0; font-variant-numeric: tabular-nums; }}
@media (max-width: 480px) {{ .grid {{ grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); }} .pair svg {{ width: 60px; height: 60px; }} }}
</style>

<div class="wrap" id="root">
  <header>
    <h1>Flower Faces</h1>
    <p class="lede">Every head-style face in <b>twemoji</b> with the face swapped for the flower. Coloured faces keep their colour in the centre; hands and features use darker shades of the petal. Drag the sliders to tune the two knobs the script exposes; the values map straight to <code>--flower-scale</code>, <code>--content-scale</code> and <code>--feature-colour</code>.</p>
  </header>

  <div class="controls">
    <div class="ctl"><label for="fs">Petal size <output id="fsv">1.00</output></label>
      <input id="fs" type="range" min="0.8" max="1.25" step="0.01" value="1"></div>
    <div class="ctl"><label for="cs">Face features <output id="csv">0.65</output></label>
      <input id="cs" type="range" min="0.5" max="1" step="0.01" value="0.65"></div>
    <div class="ctl"><label for="fc">Features <output id="fcv">{F.darken(flower.petal_fill, F.FEATURE_DARKEN)}</output></label>
      <span class="swatches"><input id="fc" type="color" value="{F.darken(flower.petal_fill, F.FEATURE_DARKEN)}">
      <button type="button" class="sw" data-c="{F.darken(flower.petal_fill, F.FEATURE_DARKEN)}" style="--c:{F.darken(flower.petal_fill, F.FEATURE_DARKEN)}" aria-label="Darkened petal" title="Darkened petal"></button>
      <button type="button" class="sw" data-c="#4a1f11" style="--c:#4a1f11" aria-label="Deeper brown" title="Deeper brown"></button>
      <button type="button" class="sw" data-c="#3d2a26" style="--c:#3d2a26" aria-label="Warm charcoal" title="Warm charcoal"></button>
      <button type="button" class="sw" data-c="#664500" style="--c:#664500" aria-label="Original twemoji brown" title="Original twemoji brown"></button></span></div>
    <label class="toggle"><input id="cmp" type="checkbox"> Show originals</label>
  </div>

  <p class="inline-demo">At text size: good morning {sample['1f60a']} that meeting was {sample['1f602']} love the new logo {sample['1f60d']} hmm {sample['1f914']} we shipped it {sample['1f973']} prod is down {sample['1f62d']} who pushed on a friday {sample['1f621']}</p>

  <p class="count">{len(tiles)} faces · {n_custom} hand-edited (sliders and colour picker don't change these)</p>
  <div class="grid">
    {''.join(tiles)}
  </div>
</div>

<script>
(() => {{
  const FX = {flower.cx:.6g}, FY = {flower.cy:.6g}, FR = {flower.outer_r:.6g};
  const fs = document.getElementById('fs'), cs = document.getElementById('cs');
  const flowers = [...document.querySelectorAll('.fz-flower')].map(g => [g, g.dataset.c.split(' ').map(Number)]);
  const contents = [...document.querySelectorAll('.fz-content')].map(g => [g, g.dataset.c.split(' ').map(Number)]);
  function apply() {{
    const f = +fs.value, c = +cs.value;
    document.getElementById('fsv').textContent = f.toFixed(2);
    document.getElementById('csv').textContent = c.toFixed(2);
    for (const [g, [x, y, r]] of flowers)
      g.setAttribute('transform', `translate(${{x}} ${{y}}) scale(${{r * f / FR}}) translate(${{-FX}} ${{-FY}})`);
    for (const [g, [x, y]] of contents)
      g.setAttribute('transform', `translate(${{x}} ${{y}}) scale(${{c}}) translate(${{-x}} ${{-y}})`);
  }}
  const fc = document.getElementById('fc'), feats = document.querySelectorAll('.fz-feat');
  function setFeat(c) {{ fc.value = c; document.getElementById('fcv').textContent = c; feats.forEach(el => el.setAttribute('fill', c)); }}
  fc.addEventListener('input', () => setFeat(fc.value));
  document.querySelectorAll('.sw').forEach(b => b.addEventListener('click', () => setFeat(b.dataset.c)));
  fs.addEventListener('input', apply); cs.addEventListener('input', apply);
  document.getElementById('cmp').addEventListener('change', e => document.getElementById('root').classList.toggle('compare', e.target.checked));
}})();
</script>
"""
args.out.write_text(page, encoding="utf-8")
print(f"{len(tiles)} tiles -> {args.out}")
