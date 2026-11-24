#!/usr/bin/env python3
"""
flowerize.py - turn yellow twemoji faces into 'flower-claude' faces.

For each twemoji SVG it finds the big yellow face disc (a <circle>, <ellipse>
or circle-shaped <path> filled with a face yellow), removes it, and draws the
flower in its place. Everything else in the emoji (eyes, mouth, hands, hats,
tears...) is kept, and can optionally be shrunk toward the face centre so it
sits inside the flower's cream centre.

No third-party dependencies - just Python 3.

Usage:
  python flowerize.py                          # every Unicode face emoji
  python flowerize.py --only 1f600 1f602       # just these codepoints
  python flowerize.py --subset                 # a small sample of faces
  python flowerize.py --content-scale 0.65 --flower-scale 1.0
"""
import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

HERE = Path(__file__).resolve().parent
# jdecked/twemoji is the maintained fork of twitter/twemoji (Emoji 17).
DEFAULT_SRC = HERE / "twemoji-jdecked" / "assets" / "svg"
DEFAULT_FLOWER = HERE / "flower.svg"
DEFAULT_OUT = HERE / "out" / "svg"

DEFAULT_EMOJI_TEST = HERE / "data" / "emoji-test.txt"

# The yellows twemoji uses for the face disc.
FACE_YELLOWS = {"#ffcc4d", "#ffcb4c", "#ffcb4d", "#ffcc4c", "#ffcb26"}

# Hand colours used on the face emoji -> how dark the replacement should be,
# as a lightness multiplier applied to the flower's petal colour.
HAND_COLOURS = {"#f19020": 0.78, "#f4900c": 0.78, "#fcab40": 0.78, "#b55005": 0.55}
# Twemoji's brown for eyes / mouths / brows (three near-identical shades).
FEATURE_BROWNS = {"#664500", "#65471b", "#66471b", "#694400"}
# Faded "motion blur" copies of the features (🫨's shaking eyes) - drawn
# between the face and feature colours, so they become cream->feature too.
GHOST_FEATURES = {"#b68600"}
GHOST_MIX = 0.45

# Tinted washes over part of the face, drawn to the face's own outline (the
# pale blue "blood draining" top of 😨 😰 😱). They need to shrink to the
# flower's centre rather than with the features, and the pale blue that
# worked on yellow gets lost on cream, so they get their own colour.
FACE_WASHES = {"#bdddf4"}
WASH_MIN_WIDTH = 28   # only shapes this wide (🧐's small monocle glint is left alone)
WASH_SCALE = 0.6
WASH_COLOUR = "#d2dfed"  # light blue, ~1.1:1 against the cream - as subtle as the original on yellow
# Features become the petal colour at this fraction of its lightness - a deep
# terracotta brown that sits with the petals instead of fighting them.
FEATURE_DARKEN = 0.38

# Darker yellows twemoji uses as drop shadows against the yellow face (behind
# hearts, halos, zzz, the thermometer, 🥸's nose, 🥳's curls). On the cream
# centre they become a blush: cream blended this far toward the petal colour.
SHADOW_YELLOWS = {"#ffac33", "#e2a62d"}
SHADOW_MIX = 0.65

# Coloured faces whose petals take a darker shade of the face colour instead
# of the usual terracotta (🤢 🥵 😡 🤬 🥶), and how dark (lightness multiplier).
PETALS_FROM_FACE = {"1f922", "1f975", "1f621", "1f92c", "1f976"}
PETAL_DARKEN = 0.75

# Faces whose oranges are not hands (🤯's explosion) keep their colours.
NO_HAND_RECOLOR = {"1f92f"}
# Faces whose meaning lives in the face outline itself (🫠 is a puddle), so a
# flower would just turn them into another smiley.
EXCLUDE = {"1fae0"}

# Unicode face subgroups we treat as "heads" (from emoji-test.txt).
FACE_SUBGROUPS = {
    "face-smiling", "face-affection", "face-tongue", "face-hand", "face-neutral-skeptical",
    "face-sleepy", "face-unwell", "face-hat", "face-glasses", "face-concerned",
    "face-negative", "face-costume",
}

SUBSET = [
    "1f600", "1f603", "1f604", "1f601", "1f606", "1f605", "1f923", "1f602",
    "1f642", "1f643", "1f609", "1f60a", "1f607", "1f970", "1f60d", "1f929",
    "1f618", "263a", "1f60b", "1f61b", "1f61c", "1f92a", "1f911", "1f917",
    "1f92d", "1f92b", "1f914", "1f610", "1f611", "1f636", "1f60f", "1f612",
    "1f644", "1f62c", "1f60c", "1f614", "1f62a", "1f924", "1f634", "1f637",
    "1f912", "1f915", "1f922", "1f927", "1f975", "1f974", "1f635", "1f92f",
    "1f920", "1f973", "1f60e", "1f913", "1f9d0", "1f615", "1f61f", "1f641",
    "1f62e", "1f62f", "1f632", "1f633", "1f97a", "1f626", "1f627", "1f628",
    "1f630", "1f625", "1f622", "1f62d", "1f631", "1f616", "1f623", "1f61e",
    "1f613", "1f629", "1f62b", "1f971", "1f624", "1f621", "1f620", "1f92c",
]


# --------------------------------------------------------------------------
# Minimal SVG path parsing -> sampled points (for bounding boxes / radii)
# --------------------------------------------------------------------------
_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_FLAG = re.compile(r"[01]")
_SEP = re.compile(r"[\s,]*")
_ARGC = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def _cubic(p0, p1, p2, p3, n=8):
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        yield (mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0],
               mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1])


def _quad(p0, p1, p2, n=8):
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        yield (mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0],
               mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1])


def _arc(p0, rx, ry, phi_deg, large, sweep, p1, n=16):
    """Sample an SVG elliptical arc (endpoint parameterisation, SVG spec F.6.5)."""
    if rx == 0 or ry == 0 or p0 == p1:
        yield p1
        return
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(phi_deg)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    k = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        k = -k
    cxp, cyp = k * rx * y1p / ry, -k * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (p0[0] + p1[0]) / 2
    cy = sp * cxp + cp * cyp + (p0[1] + p1[1]) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    for i in range(1, n + 1):
        t = t1 + dt * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        yield (cp * x - sp * y + cx, sp * x + cp * y + cy)


def path_points(d):
    """Return a list of points sampled along path `d` (absolute coords)."""
    pos = 0
    L = len(d)

    def skip():
        nonlocal pos
        pos = _SEP.match(d, pos).end()

    def read(rx):
        nonlocal pos
        skip()
        m = rx.match(d, pos)
        if not m:
            return None
        pos = m.end()
        return float(m.group())

    pts = []
    cmd = None
    cur = start = (0.0, 0.0)
    last_ctrl = None
    last_cmd = ""
    while True:
        skip()
        if pos >= L:
            break
        if d[pos].isalpha():
            cmd = d[pos]
            pos += 1
            if cmd in "Zz":
                cur = start
                pts.append(cur)
                last_cmd = "Z"
                continue
        if cmd is None or cmd in "Zz":
            break
        up = cmd.upper()
        if up == "A":
            a = [read(_NUM), read(_NUM), read(_NUM), read(_FLAG), read(_FLAG), read(_NUM), read(_NUM)]
        else:
            a = [read(_NUM) for _ in range(_ARGC[up])]
        if any(v is None for v in a):
            break
        rel = cmd.islower()
        ox, oy = cur if rel else (0.0, 0.0)
        if up == "M":
            cur = (ox + a[0], oy + a[1])
            start = cur
            pts.append(cur)
            cmd = "l" if rel else "L"  # implicit lineto after moveto
            last_ctrl = None
        elif up == "L":
            cur = (ox + a[0], oy + a[1])
            pts.append(cur)
            last_ctrl = None
        elif up == "H":
            cur = ((cur[0] if rel else 0.0) + a[0], cur[1])
            pts.append(cur)
            last_ctrl = None
        elif up == "V":
            cur = (cur[0], (cur[1] if rel else 0.0) + a[0])
            pts.append(cur)
            last_ctrl = None
        elif up == "C":
            p1 = (ox + a[0], oy + a[1]); p2 = (ox + a[2], oy + a[3]); p3 = (ox + a[4], oy + a[5])
            pts.extend(_cubic(cur, p1, p2, p3)); last_ctrl = p2; cur = p3
        elif up == "S":
            p1 = (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1]) if last_cmd in "CS" and last_ctrl else cur
            p2 = (ox + a[0], oy + a[1]); p3 = (ox + a[2], oy + a[3])
            pts.extend(_cubic(cur, p1, p2, p3)); last_ctrl = p2; cur = p3
        elif up == "Q":
            p1 = (ox + a[0], oy + a[1]); p2 = (ox + a[2], oy + a[3])
            pts.extend(_quad(cur, p1, p2)); last_ctrl = p1; cur = p2
        elif up == "T":
            p1 = (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1]) if last_cmd in "QT" and last_ctrl else cur
            p2 = (ox + a[0], oy + a[1])
            pts.extend(_quad(cur, p1, p2)); last_ctrl = p1; cur = p2
        elif up == "A":
            p2 = (ox + a[5], oy + a[6])
            pts.extend(_arc(cur, a[0], a[1], a[2], int(a[3]), int(a[4]), p2))
            cur = p2
            last_ctrl = None
        last_cmd = up
    return pts


def bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# --------------------------------------------------------------------------
# Colour helpers
# --------------------------------------------------------------------------
def _hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def darken(hex_colour, factor):
    """Scale HSL lightness of `hex_colour` by `factor` (keeps hue + saturation)."""
    import colorsys
    r, g, b = _hex_to_rgb(hex_colour)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, l * factor, s)
    return "#{:02x}{:02x}{:02x}".format(*(round(v * 255) for v in (r, g, b)))


def mix(hex_a, hex_b, t):
    """Blend from colour a (t=0) to colour b (t=1)."""
    a, b = _hex_to_rgb(hex_a), _hex_to_rgb(hex_b)
    return "#" + "".join("{:02x}".format(round((x + (y - x) * t) * 255)) for x, y in zip(a, b))


# --------------------------------------------------------------------------
# Which twemoji files are faces
# --------------------------------------------------------------------------
def twemoji_name(codes):
    """twemoji file naming: drop FE0F unless the sequence contains a ZWJ."""
    codes = [c.lower() for c in codes]
    if "200d" not in codes:
        codes = [c for c in codes if c != "fe0f"]
    return "-".join(codes)


def face_names(emoji_test=DEFAULT_EMOJI_TEST):
    """File stems of every fully-qualified emoji in the Unicode face-* subgroups."""
    names, sub = [], None
    for line in Path(emoji_test).read_text(encoding="utf-8").splitlines():
        m = re.match(r"# subgroup: (\S+)", line)
        if m:
            sub = m.group(1)
        elif sub in FACE_SUBGROUPS and "; fully-qualified" in line:
            name = twemoji_name(line.split(";")[0].split())
            if name not in EXCLUDE:
                names.append(name)
    return names


def readable_names(emoji_test=DEFAULT_EMOJI_TEST):
    """{twemoji file stem: 'claude-<unicode-name>'}, e.g. '1f600' -> 'claude-grinning-face'."""
    out = {}
    for line in Path(emoji_test).read_text(encoding="utf-8").splitlines():
        m = re.match(r"([0-9A-F ]+?)\s*;\s*[\w-]+\s*#\s*\S+\s+E[\d.]+\s+(.*)", line)
        if m:
            slug = re.sub(r"[^a-z0-9]+", "-", m.group(2).lower().replace("’", "")).strip("-")
            out.setdefault(twemoji_name(m.group(1).split()), "claude-" + slug)
    return out


def codes_by_readable_name(emoji_test=DEFAULT_EMOJI_TEST):
    """Inverse of readable_names: 'claude-grinning-face' -> '1f600' (fully-qualified form wins)."""
    out = {}
    for code, name in readable_names(emoji_test).items():
        out.setdefault(name, code)
    return out


# --------------------------------------------------------------------------
# Flower
# --------------------------------------------------------------------------
class Flower:
    def __init__(self, path):
        root = ET.parse(path).getroot()
        style = "".join(e.text or "" for e in root.iter(f"{{{SVG_NS}}}style"))
        classes = dict(re.findall(r"\.(\w+)\s*\{\s*fill:\s*(#[0-9a-fA-F]+)", style))
        paths = list(root.iter(f"{{{SVG_NS}}}path"))
        if len(paths) < 2:
            sys.exit("flower svg should contain a petal path and a centre path")
        self.shapes = []
        for p in paths:
            fill = p.get("fill") or classes.get(p.get("class", ""), "#000")
            self.shapes.append((p.get("d"), fill, p.get("fill-rule")))
        # the centre is the last path (the cream disc)
        cx0, cy0, cx1, cy1 = bbox(path_points(self.shapes[-1][0]))
        self.cx, self.cy = (cx0 + cx1) / 2, (cy0 + cy1) / 2
        self.center_r = (cx1 - cx0 + cy1 - cy0) / 4
        self.center_fill = self.shapes[-1][1]
        petal_pts = path_points(self.shapes[0][0])
        self.outer_r = max(math.hypot(x - self.cx, y - self.cy) for x, y in petal_pts)

        self.petal_fill = self.shapes[0][1]

    def group(self, cx, cy, radius, center_fill=None, petal_fill=None):
        """An SVG <g> with the flower centred on (cx,cy), petal tips at `radius`."""
        s = radius / self.outer_r
        g = ET.Element(f"{{{SVG_NS}}}g", {
            "transform": f"translate({cx:g} {cy:g}) scale({s:.6g}) translate({-self.cx:.6g} {-self.cy:.6g})"
        })
        last = len(self.shapes) - 1
        for i, (d, fill, rule) in enumerate(self.shapes):
            if i == last and center_fill:
                fill = center_fill
            elif i == 0 and petal_fill:
                fill = petal_fill
            attrs = {"fill": fill, "d": d}
            if rule:
                attrs["fill-rule"] = rule
            ET.SubElement(g, f"{{{SVG_NS}}}path", attrs)
        return g


# --------------------------------------------------------------------------
# Face detection + rewrite
# --------------------------------------------------------------------------
def local(tag):
    return tag.split("}", 1)[-1]


def element_disc(el):
    """If `el` is a roughly circular shape, return (cx, cy, r); else None."""
    t = local(el.tag)
    try:
        if t == "circle":
            return float(el.get("cx", 0)), float(el.get("cy", 0)), float(el.get("r"))
        if t == "ellipse":
            rx, ry = float(el.get("rx")), float(el.get("ry"))
            if abs(rx - ry) / max(rx, ry) > 0.08:
                return None
            return float(el.get("cx", 0)), float(el.get("cy", 0)), (rx + ry) / 2
        if t == "path":
            pts = path_points(el.get("d", ""))
            if len(pts) < 4:
                return None
            x0, y0, x1, y1 = bbox(pts)
            w, h = x1 - x0, y1 - y0
            if min(w, h) <= 0 or abs(w - h) / max(w, h) > 0.08:
                return None
            cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, (w + h) / 4
            # every sampled point should lie close to the circle
            if max(abs(math.hypot(x - cx, y - cy) - r) for x, y in pts) > 0.06 * r:
                return None
            return cx, cy, r
    except (TypeError, ValueError):
        return None
    return None


def find_face(root):
    """Find the face shape. Returns (element, (cx, cy, r), fill, top-level element)
    or all Nones.

    1. A big disc (circle / ellipse / circular path) of any colour - covers the
       yellow faces plus green, red, blue, purple and clown faces.
    2. Otherwise a big face-yellow shape that isn't a clean circle (😱 has its
       hands cut out, 🤯 has its top blown off). The flower is fitted to the
       bottom/sides of its bounding box.
    """
    for el, top in _candidates(root):
        if el.get("transform") or not el.get("fill"):
            continue
        disc = element_disc(el)
        if disc and disc[2] >= 11:  # face discs are r≈17-18 in a 36 viewBox (🫨: 12)
            return el, disc, el.get("fill"), top
    for el, top in _candidates(root):
        fill = (el.get("fill") or "").lower()
        if fill not in FACE_YELLOWS or el.get("transform") or local(el.tag) != "path":
            continue
        pts = path_points(el.get("d", ""))
        if len(pts) < 4:
            continue
        x0, y0, x1, y1 = bbox(pts)
        if x1 - x0 >= 28 and y1 - y0 >= 20:
            r = (x1 - x0) / 2
            return el, ((x0 + x1) / 2, y1 - r, r), el.get("fill"), top
    return None, None, None, None


def _candidates(root):
    """Top-level shapes, plus shapes one level down inside a plain <g> (🫨 keeps
    its face inside a clipped group). Yields (element, its top-level element)."""
    for el in list(root):
        if local(el.tag) == "g" and not el.get("transform"):
            for sub in list(el):
                yield sub, el
        else:
            yield el, el


def flowerize(svg_text, flower, flower_scale=1.0, content_scale=0.65, recolor_yellow=True,
              recolor_hands=True, feature_fill="auto", shadow_mix=SHADOW_MIX, petal_darken=None,
              wash_scale=WASH_SCALE, wash_fill=WASH_COLOUR, tag=False):
    """Return the flowerized SVG text, or None if no face shape was found.

    tag=True marks the flower / content groups with classes + data attributes
    (used by the preview page's sliders); leave it off for real output.
    """
    root = ET.fromstring(svg_text)
    face, disc, face_fill, top = find_face(root)
    if face is None:
        return None
    cx, cy, r = disc
    is_yellow = face_fill.lower() in FACE_YELLOWS
    # yellow faces get the flower's own centre; coloured faces (🤢 😡 🥶 😈 🤡)
    # keep their colour in the centre so they still read as sick / angry / cold.
    center_fill = flower.center_fill if is_yellow else face_fill
    hand_map = {c: darken(flower.petal_fill, k) for c, k in HAND_COLOURS.items()} if recolor_hands else {}
    if feature_fill == "auto":
        feature_fill = darken(flower.petal_fill, FEATURE_DARKEN)
    shadow_fill = mix(flower.center_fill, flower.petal_fill, shadow_mix) if shadow_mix is not None else None
    ghost_fill = mix(center_fill, feature_fill, GHOST_MIX) if feature_fill and is_yellow else None

    children = list(root)
    idx = children.index(top)
    for el in children:
        root.remove(el)
    if top is face:
        before, after = children[:idx], children[idx + 1:]
    else:
        # face lives inside a group (maybe clipped): take it out and put the
        # flower before the group at top level so the clip can't cut the petals
        top.remove(face)
        before, after = children[:idx], children[idx:]

    def wrap(elements):
        if not elements:
            return []
        for el in elements:
            for sub in el.iter():
                fill = (sub.get("fill") or "").lower()
                if recolor_yellow and is_yellow and fill in FACE_YELLOWS:
                    sub.set("fill", center_fill)
                elif shadow_fill and is_yellow and fill in SHADOW_YELLOWS:
                    sub.set("fill", shadow_fill)
                elif fill in hand_map:
                    sub.set("fill", hand_map[fill])
                elif ghost_fill and fill in GHOST_FEATURES:
                    sub.set("fill", ghost_fill)
                elif feature_fill and fill in FEATURE_BROWNS:
                    sub.set("fill", feature_fill)
                    if tag:
                        sub.set("class", "fz-feat")
        # group consecutive elements by the scale they need, keeping paint order
        runs = []
        for el in elements:
            kind = "wash" if is_wash(el) else "content"
            if kind == "wash" and wash_fill:
                el.set("fill", wash_fill)
            if runs and runs[-1][0] == kind:
                runs[-1][1].append(el)
            else:
                runs.append((kind, [el]))
        out = []
        for kind, els in runs:
            k = wash_scale if kind == "wash" else content_scale
            if abs(k - 1) < 1e-9 and not tag:
                out.extend(els)
                continue
            g = ET.Element(f"{{{SVG_NS}}}g", {
                "transform": f"translate({cx:g} {cy:g}) scale({k:g}) translate({-cx:g} {-cy:g})"
            })
            if tag:
                g.set("class", "fz-content" if kind == "content" else "fz-wash")
                g.set("data-c", f"{cx:g} {cy:g}")
            g.extend(els)
            out.append(g)
        return out

    def is_wash(el):
        if (el.get("fill") or "").lower() not in FACE_WASHES or el.get("transform") or not el.get("d"):
            return False
        x0, _, x1, _ = bbox(path_points(el.get("d")) or [(0, 0)])
        return x1 - x0 >= WASH_MIN_WIDTH

    before = wrap(before)
    after = wrap(after)
    for el in before:
        root.append(el)
    petal_fill = darken(face_fill, petal_darken) if petal_darken and not is_yellow else None
    fg = flower.group(cx, cy, r * flower_scale, center_fill, petal_fill)
    if tag:
        fg.set("class", "fz-flower")
        fg.set("data-c", f"{cx:g} {cy:g} {r:g}")
    root.append(fg)
    for el in after:
        root.append(el)
    return ET.tostring(root, encoding="unicode")


def process_file(path, flower, **kw):
    """flowerize() a twemoji file, honouring the per-emoji exceptions."""
    if path.stem in NO_HAND_RECOLOR:
        kw["recolor_hands"] = False
    if path.stem in PETALS_FROM_FACE:
        kw.setdefault("petal_darken", PETAL_DARKEN)
    return flowerize(path.read_text(encoding="utf-8"), flower, **kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC, help="twemoji assets/svg folder")
    ap.add_argument("--flower", type=Path, default=DEFAULT_FLOWER, help="flower svg")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output folder")
    ap.add_argument("--emoji-test", type=Path, default=DEFAULT_EMOJI_TEST,
                    help="Unicode emoji-test.txt, used to pick out the face emoji")
    ap.add_argument("--flower-scale", type=float, default=1.0,
                    help="petal-tip radius as a multiple of the original face radius (default 1.0)")
    ap.add_argument("--content-scale", type=float, default=0.65,
                    help="shrink eyes/mouth/etc toward the centre by this factor (default 0.65)")
    ap.add_argument("--no-recolor", action="store_true",
                    help="don't recolour other face-yellow bits (eyelids etc) to the flower centre colour")
    ap.add_argument("--no-hands", action="store_true",
                    help="keep the original orange hands instead of darkened petal colour")
    ap.add_argument("--feature-colour", default="auto",
                    help="colour for eyes/mouths: 'auto' (darkened petal), a hex like '#5c2716', "
                         "or 'keep' for twemoji's original brown")
    ap.add_argument("--shadow-mix", default=str(SHADOW_MIX),
                    help="shadow shade (behind hearts, halos, zzz...) as a 0-1 blend from the flower "
                         f"centre to the petal colour (default {SHADOW_MIX}), or 'keep' for twemoji's amber")
    ap.add_argument("--wash-scale", type=float, default=WASH_SCALE,
                    help=f"scale for the pale-blue face washes on 😨 😰 😱 (default {WASH_SCALE})")
    ap.add_argument("--wash-colour", default=WASH_COLOUR,
                    help=f"colour for those washes (default {WASH_COLOUR}), or 'keep' for twemoji's pale blue")
    sel = ap.add_mutually_exclusive_group()
    sel.add_argument("--only", nargs="+", metavar="CODE", help="only these file names (without .svg)")
    sel.add_argument("--subset", action="store_true", help="only a built-in sample of faces")
    args = ap.parse_args()

    flower = Flower(args.flower)
    args.out.mkdir(parents=True, exist_ok=True)

    if args.only:
        names = args.only
    elif args.subset:
        names = SUBSET
    else:
        names = face_names(args.emoji_test)

    readable = readable_names(args.emoji_test)
    done, skipped = [], []
    for name in names:
        f = args.src / f"{name}.svg"
        out = process_file(f, flower, flower_scale=args.flower_scale, content_scale=args.content_scale,
                           recolor_yellow=not args.no_recolor, recolor_hands=not args.no_hands,
                           feature_fill=None if args.feature_colour == "keep" else args.feature_colour,
                           shadow_mix=None if args.shadow_mix == "keep" else float(args.shadow_mix),
                           wash_scale=args.wash_scale,
                           wash_fill=None if args.wash_colour == "keep" else args.wash_colour)             if f.exists() else None
        if out is None:
            skipped.append(name)
            continue
        (args.out / f"{readable.get(name, name)}.svg").write_text(out, encoding="utf-8")
        done.append(name)

    print(f"flowerized {len(done)} emoji -> {args.out}")
    if skipped:
        print("skipped (no head shape found):", " ".join(skipped))


if __name__ == "__main__":
    main()
