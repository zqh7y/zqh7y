#!/usr/bin/env python3
"""Generate assets/stats.svg: four floating 3D stat slabs with odometer counters.

Deterministic, stdlib only. Run:  python3 src/stats.py

How the "3D" works
------------------
Each card is a rounded slab (front face + extruded body). Its pose (yaw, lean,
bob) is sampled at N frames over one loop. For every frame the slab is pushed
through a rotation and a para-perspective projection (perspective linearised
at the card centre), which yields an exact affine map from card-local (u, v)
coordinates to screen. That affine map is decomposed into
translate * rotate * skewX * scale and animated with SMIL animateTransform, so
the face, its text, the odometer, masks and the sheen all live in local
coordinates and stay glued together.

The extruded body of a convex shape swept along a vector d is
  shape ∪ (shape + d) ∪ quad(p1, p1 + d, p2 + d, p2)
where p1/p2 are the support points perpendicular to d. We draw the back face
(translated rounded rect) plus that quad, then the front face on top.
"""
import math
import os
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets", "stats.svg")

# ---------------------------------------------------------------- palette
INK = "#0b0b0c"
PANEL = "#141416"
HAIR = "#26262b"
TEXT = "#f5f5f2"
MUTED = "#8a8a90"
LIME = "#d4ff3a"
LIME2 = "#b8f000"
HOLO = ("#7af0ff", "#b48cff", "#ff8ad8")

SANS = "'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

# ---------------------------------------------------------------- canvas
VW, VH = 1000, 210
PERIOD = 10.0           # seconds, motion loop (wobble / bob / sheen)
ODO_PERIOD = 10.0       # seconds, odometer loop
NF = 60                 # pose samples per loop

# camera for para-perspective
CAM_X, CAM_Y, FOCAL = 500.0, 92.0, 1500.0

H = 140                 # card face height (local units)
DEPTH = 24.0            # slab thickness
RADIUS = 18.0
LEAN0, LEAN_AMP = 13.0, 3.5     # degrees (top tilts away -> bottom edge shows)
YAW0, YAW_AMP = -7.0, 6.0       # degrees (negative -> right edge shows)
BOB_AMP = 4.0
LIP = 0.32              # fraction of the slab depth drawn as a bright lip

VAL_FS = 62.0           # value font size
VAL_BASE = 90.0         # value baseline (local)
LABEL_FS = 18.0
LABEL_BASE = H - 17.0
COL_W = VAL_FS * 0.58   # odometer column advance
LINE_H = VAL_FS * 1.16  # odometer strip pitch
PAD = 20.0

CARDS = [
    dict(w=204, digits="13", suffix="", label="react native apps", tag="01",
         icon="phone", lime=False),
    dict(w=204, digits="5", suffix="", label="on google play", tag="02",
         icon="play", lime=False),
    dict(w=246, digits="10", suffix="K+", label="downloads · virtual live",
         tag="03", icon="download", lime=True),
    dict(w=204, digits="4", suffix="y", label="shipping since 2022", tag="04",
         icon="clock", lime=False),
]
GAP = 28.0
CARD_CY = 90.0

# Rough Arial/Helvetica advance widths (em) used to pin label widths with
# textLength, so every viewer's fallback font lands on the same width.
_W = {
    " ": .278, "·": .278, "a": .556, "b": .556, "c": .5, "d": .556,
    "e": .556, "f": .278, "g": .556, "h": .556, "i": .222, "j": .222,
    "k": .5, "l": .222, "m": .833, "n": .556, "o": .556, "p": .556,
    "q": .556, "r": .333, "s": .5, "t": .278, "u": .556, "v": .5, "w": .722,
    "x": .5, "y": .5, "z": .5, "0": .556, "1": .556, "2": .556, "3": .556,
    "4": .556, "5": .556, "6": .556, "7": .556, "8": .556, "9": .556,
}


def text_w(s, fs):
    return sum(_W.get(ch, .6) for ch in s) * fs


def f(x, nd=2):
    """Compact number formatting."""
    s = f"{x:.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    return s


# ---------------------------------------------------------------- 3D math
def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b)))
             for j in range(len(b[0]))] for i in range(len(a))]


def rotation(yaw_deg, lean_deg):
    y = math.radians(yaw_deg)
    l = math.radians(lean_deg)
    # yaw about the vertical axis: +yaw sends the right edge away (+z)
    r_yaw = [[math.cos(y), 0, -math.sin(y)],
             [0, 1, 0],
             [math.sin(y), 0, math.cos(y)]]
    # lean about the horizontal axis: +lean sends the top edge away (+z)
    r_lean = [[1, 0, 0],
              [0, math.cos(l), math.sin(l)],
              [0, -math.sin(l), math.cos(l)]]
    return mat_mul(r_lean, r_yaw)


def pose_affine(cx, cy, w, yaw, lean):
    """Affine (a,b,c,d,e,f) local->screen and the screen depth vector."""
    r = rotation(yaw, lean)
    # Jacobian of perspective projection at the card centre (z = 0 plane)
    j = [[1.0, 0.0, -(cx - CAM_X) / FOCAL],
         [0.0, 1.0, -(cy - CAM_Y) / FOCAL]]
    jr = mat_mul(j, r)                      # 2x3
    a, b = jr[0][0], jr[1][0]               # image of local x axis
    c, d = jr[0][1], jr[1][1]               # image of local y axis
    dz = (jr[0][2] * DEPTH, jr[1][2] * DEPTH)  # image of the depth vector
    e = cx - (a * w / 2 + c * H / 2)
    f_ = cy - (b * w / 2 + d * H / 2)
    return (a, b, c, d, e, f_), dz


def decompose(m):
    a, b, c, d, e, f_ = m
    sx = math.hypot(a, b)
    th = math.atan2(b, a)
    cp = math.cos(th) * c + math.sin(th) * d
    dp = -math.sin(th) * c + math.cos(th) * d
    sy = dp
    skew = math.degrees(math.atan2(cp, sy))
    return e, f_, math.degrees(th), skew, sx, sy


def local_of(m, vec):
    a, b, c, d, _, _ = m
    det = a * d - b * c
    x, y = vec
    return ((d * x - c * y) / det, (-b * x + a * y) / det)


def support(w, n):
    """Support point of the rounded rect [0,w]x[0,H] (radius RADIUS) along n."""
    nx, ny = n
    ln = math.hypot(nx, ny) or 1.0
    px = (w - RADIUS) if nx > 0 else RADIUS
    py = (H - RADIUS) if ny > 0 else RADIUS
    return px + RADIUS * nx / ln, py + RADIUS * ny / ln


# ---------------------------------------------------------------- svg helpers
def kt_list(ts):
    return ";".join(f(t, 4) for t in ts)


def anim_values(vals):
    return ";".join(vals)


class Doc:
    def __init__(self):
        self.defs = []
        self.body = []

    def d(self, s):
        self.defs.append(s)

    def b(self, s):
        self.body.append(s)


def odometer_column(seq_len, start, dur, out_start, out_dur, overshoot=0.16):
    """keyTimes/values/keySplines for one strip.

    Strip rows: 0 = blank, 1..seq_len = digits (last is the target),
    seq_len + 1 = blank. Rolls from row 0 to row seq_len with a tiny
    overshoot + settle, holds, then rolls one more row up (to blank) and
    the loop restarts on the (identical) blank row 0.
    """
    T = ODO_PERIOD
    m = seq_len
    t0 = start / T
    t1 = (start + dur * 0.86) / T
    t2 = (start + dur) / T
    t3 = out_start / T
    t4 = (out_start + out_dur) / T
    ys = [0, 0, -(m + overshoot) * LINE_H, -m * LINE_H, -m * LINE_H,
          -(m + 1) * LINE_H, -(m + 1) * LINE_H]
    kts = [0, t0, t1, t2, t3, t4, 1]
    lin = "0 0 1 1"
    splines = [lin,
               "0.2 0.55 0.3 1",      # fast spin, long ease-out
               "0.4 0 0.4 1",         # settle back from overshoot
               lin,
               "0.55 0 0.75 0.35",    # roll away (ease-in)
               lin]
    vals = ";".join(f"0 {f(y)}" for y in ys)
    return kts, vals, ";".join(splines)


def icon_svg(kind, x, y, color):
    """18x18-ish icons drawn at (x, y) top-left, local coords."""
    sw = 1.9
    common = (f'fill="none" stroke="{color}" stroke-width="{sw}" '
              f'stroke-linecap="round" stroke-linejoin="round"')
    if kind == "phone":
        return (f'<g transform="translate({f(x)} {f(y)})" {common}>'
                f'<rect x="3.5" y="0" width="12" height="19" rx="3"/>'
                f'<path d="M7.8 15.6h3.4"/></g>')
    if kind == "play":
        return (f'<g transform="translate({f(x)} {f(y)})" {common}>'
                f'<path d="M3.5 1.2v16.6c0 .8.8 1.2 1.4.8l12.6-7.8'
                f'c.6-.4.6-1.2 0-1.6L4.9.4c-.6-.4-1.4 0-1.4.8z"/></g>')
    if kind == "download":
        return (f'<g transform="translate({f(x)} {f(y)})" {common}>'
                f'<path d="M9.5 1v11.5M4.5 8l5 5 5-5M2 18.2h15"/></g>')
    if kind == "clock":
        return (f'<g transform="translate({f(x)} {f(y)})" {common}>'
                f'<circle cx="9.5" cy="9.5" r="8.6"/>'
                f'<path d="M9.5 4.6v5.2l3.4 2"/></g>')
    return ""


# ---------------------------------------------------------------- build
def build():
    doc = Doc()
    total_w = sum(c["w"] for c in CARDS) + GAP * (len(CARDS) - 1)
    x = (VW - total_w) / 2
    for c in CARDS:
        c["cx"] = x + c["w"] / 2
        x += c["w"] + GAP

    # --- global defs
    doc.d(f'''<linearGradient id="bgGlow" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#101012"/><stop offset="1" stop-color="{INK}"/>
</linearGradient>
<radialGradient id="floorL" cx="0.5" cy="0.5" r="0.5">
  <stop offset="0" stop-color="{LIME}" stop-opacity="0.38"/>
  <stop offset="0.55" stop-color="{LIME}" stop-opacity="0.10"/>
  <stop offset="1" stop-color="{LIME}" stop-opacity="0"/>
</radialGradient>
<radialGradient id="floorH" cx="0.5" cy="0.5" r="0.5">
  <stop offset="0" stop-color="{HOLO[1]}" stop-opacity="0.30"/>
  <stop offset="0.55" stop-color="{HOLO[0]}" stop-opacity="0.08"/>
  <stop offset="1" stop-color="{HOLO[0]}" stop-opacity="0"/>
</radialGradient>
<pattern id="dots" width="20" height="20" patternUnits="userSpaceOnUse">
  <circle cx="1" cy="1" r="1" fill="#ffffff" fill-opacity="0.045"/>
</pattern>
<clipPath id="frame"><rect width="{VW}" height="{VH}" rx="22"/></clipPath>
<linearGradient id="sheenG" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="#fff" stop-opacity="0"/>
  <stop offset="0.5" stop-color="#fff" stop-opacity="0.16"/>
  <stop offset="1" stop-color="#fff" stop-opacity="0"/>
</linearGradient>
<linearGradient id="sheenInk" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="#fff" stop-opacity="0"/>
  <stop offset="0.5" stop-color="#fff" stop-opacity="0.55"/>
  <stop offset="1" stop-color="#fff" stop-opacity="0"/>
</linearGradient>
<linearGradient id="digitG" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#c9c9cf"/>
</linearGradient>
<linearGradient id="faceD" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#1c1c20"/><stop offset="1" stop-color="{PANEL}"/>
</linearGradient>
<linearGradient id="faceL" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#e2ff6e"/><stop offset="0.6" stop-color="{LIME}"/>
  <stop offset="1" stop-color="#c6f024"/>
</linearGradient>
<radialGradient id="holoTint" cx="1" cy="0" r="0.9">
  <stop offset="0" stop-color="{HOLO[1]}" stop-opacity="0.16"/>
  <stop offset="0.5" stop-color="{HOLO[0]}" stop-opacity="0.04"/>
  <stop offset="1" stop-color="{HOLO[0]}" stop-opacity="0"/>
</radialGradient>''')

    doc.b(f'<rect width="{VW}" height="{VH}" rx="22" fill="url(#bgGlow)"/>')
    doc.b(f'<g clip-path="url(#frame)">')
    doc.b(f'<rect width="{VW}" height="{VH}" fill="url(#dots)"/>')

    floor_y = CARD_CY + H / 2 + 26

    for i, c in enumerate(CARDS):
        w = c["w"]
        cid = f"c{i}"
        lime = c["lime"]
        phase = i * 0.9  # radians, staggers the wobble/bob between cards

        # ---------- sample poses
        tr_vals, rot_vals, skew_vals, sc_vals = [], [], [], []
        back_vals, quad_vals, grad_vals = [], [], []
        floor_s, floor_o = [], []
        static_m = []
        lip_vals = []
        for k in range(NF + 1):
            t = k / NF
            ang = 2 * math.pi * t
            yaw = YAW0 + YAW_AMP * math.sin(ang + phase)
            lean = LEAN0 + LEAN_AMP * math.cos(ang + phase)
            bob = BOB_AMP * math.sin(2 * ang + phase * 1.7)
            cx, cy = c["cx"], CARD_CY - bob
            m, dz = pose_affine(cx, cy, w, yaw, lean)
            static_m.append(m)
            e, f_, th, sk, sx, sy = decompose(m)
            tr_vals.append(f"{f(e)} {f(f_)}")
            rot_vals.append(f(th, 3))
            skew_vals.append(f(sk, 3))
            sc_vals.append(f"{f(sx, 4)} {f(sy, 4)}")
            dl = local_of(m, dz)
            back_vals.append(f"{f(dl[0])} {f(dl[1])}")
            lip_vals.append(f"{f(dl[0] * LIP)} {f(dl[1] * LIP)}")
            n = (dl[1], -dl[0])
            p1 = support(w, n)
            p2 = support(w, (-n[0], -n[1]))
            pts = [p1, (p1[0] + dl[0], p1[1] + dl[1]),
                   (p2[0] + dl[0], p2[1] + dl[1]), p2]
            quad_vals.append(" ".join(f"{f(px)},{f(py)}" for px, py in pts))
            # holographic foil shifts with viewing angle
            grad_vals.append(f"{f((yaw - YAW0) * 4.0)} {f((lean - LEAN0) * 3.0)}")
            # floor glow: smaller + dimmer when the card is higher
            h01 = (bob + BOB_AMP) / (2 * BOB_AMP)
            floor_s.append(f"{f(1.0 - 0.12 * h01, 3)} 1")
            floor_o.append(f(0.95 - 0.35 * h01, 3))

        dur = f"{f(PERIOD)}s"
        rep = 'repeatCount="indefinite"'

        # ---------- per-card defs
        if lime:
            doc.d(f'''<linearGradient id="side{i}" gradientUnits="userSpaceOnUse" x1="0" y1="{H}" x2="{w}" y2="0" spreadMethod="reflect">
  <stop offset="0" stop-color="#6c8a00"/><stop offset="0.22" stop-color="{LIME2}"/>
  <stop offset="0.42" stop-color="#7f9f00"/><stop offset="0.6" stop-color="#e9ff8f"/>
  <stop offset="0.78" stop-color="#9cc400"/><stop offset="1" stop-color="#5f7a00"/>
  <animateTransform attributeName="gradientTransform" type="translate" dur="{dur}" {rep} values="{anim_values(grad_vals)}"/>
</linearGradient>''')
        else:
            doc.d(f'''<linearGradient id="side{i}" gradientUnits="userSpaceOnUse" x1="0" y1="{H}" x2="{w}" y2="0" spreadMethod="reflect">
  <stop offset="0" stop-color="#1d4a55"/><stop offset="0.16" stop-color="{HOLO[0]}"/>
  <stop offset="0.34" stop-color="#3a2d6e"/><stop offset="0.52" stop-color="{HOLO[1]}"/>
  <stop offset="0.7" stop-color="{HOLO[2]}"/><stop offset="0.86" stop-color="#4a1f45"/>
  <stop offset="1" stop-color="{LIME}"/>
  <animateTransform attributeName="gradientTransform" type="translate" dur="{dur}" {rep} values="{anim_values(grad_vals)}"/>
</linearGradient>''')
        doc.d(f'<clipPath id="face{i}"><rect width="{w}" height="{H}" rx="{RADIUS}"/></clipPath>')
        # odometer window: tight, with short soft fades top/bottom (drum).
        wy0 = VAL_BASE - VAL_FS * 0.80
        wy1 = VAL_BASE + 6.0
        hgt = wy1 - wy0
        o_top = 5.0 / hgt
        o_bot = (VAL_BASE + 2.0 - wy0) / hgt
        doc.d(f'''<linearGradient id="drum{i}G" gradientUnits="userSpaceOnUse" x1="0" y1="{f(wy0)}" x2="0" y2="{f(wy1)}">
  <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="{f(o_top, 3)}" stop-color="#fff"/>
  <stop offset="{f(o_bot, 3)}" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
</linearGradient>
<mask id="drum{i}" maskUnits="userSpaceOnUse" x="0" y="{f(wy0)}" width="{w}" height="{f(hgt)}">
  <rect x="0" y="{f(wy0)}" width="{w}" height="{f(hgt)}" fill="url(#drum{i}G)"/>
</mask>''')
        if c["suffix"]:
            # suffix window: same soft top edge as the drum (it rolls out
            # upward through it), but open at the bottom so the descender
            # of "y" is never clipped. Stops above the label.
            sy1 = LABEL_BASE - LABEL_FS * 0.8
            shg = sy1 - wy0
            doc.d(f'''<linearGradient id="suf{i}G" gradientUnits="userSpaceOnUse" x1="0" y1="{f(wy0)}" x2="0" y2="{f(sy1)}">
  <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="{f(5.0 / shg, 3)}" stop-color="#fff"/>
  <stop offset="1" stop-color="#fff"/>
</linearGradient>
<mask id="suf{i}" maskUnits="userSpaceOnUse" x="0" y="{f(wy0)}" width="{w}" height="{f(shg)}">
  <rect x="0" y="{f(wy0)}" width="{w}" height="{f(shg)}" fill="url(#suf{i}G)"/>
</mask>''')

        # ---------- floor glow (screen space)
        fg = "floorL" if lime else "floorH"
        fx = c["cx"]
        doc.b(f'<g transform="translate({f(fx)} {f(floor_y)})">'
              f'<ellipse rx="{f(w * 0.55)}" ry="13" fill="url(#{fg})">'
              f'<animateTransform attributeName="transform" type="scale" dur="{dur}" {rep} values="{anim_values(floor_s)}"/>'
              f'<animate attributeName="opacity" dur="{dur}" {rep} values="{anim_values(floor_o)}"/>'
              f'</ellipse></g>')

        # ---------- the slab (local coords under an animated affine)
        # static transform = frame 0, so renderers without SMIL still see a
        # correctly posed card; the first animation replaces it, the rest
        # post-multiply onto that.
        m0 = static_m[0]
        doc.b(f'<g id="{cid}" transform="matrix({" ".join(f(v, 4) for v in m0)})">')
        doc.b(f'<animateTransform attributeName="transform" type="translate" dur="{dur}" {rep} values="{anim_values(tr_vals)}"/>')
        doc.b(f'<animateTransform attributeName="transform" type="rotate" additive="sum" dur="{dur}" {rep} values="{anim_values(rot_vals)}"/>')
        doc.b(f'<animateTransform attributeName="transform" type="skewX" additive="sum" dur="{dur}" {rep} values="{anim_values(skew_vals)}"/>')
        doc.b(f'<animateTransform attributeName="transform" type="scale" additive="sum" dur="{dur}" {rep} values="{anim_values(sc_vals)}"/>')

        # body: back face + bridge quad, same foil gradient
        doc.b(f'<rect width="{w}" height="{H}" rx="{RADIUS}" fill="url(#side{i})" transform="translate({back_vals[0]})">'
              f'<animateTransform attributeName="transform" type="translate" dur="{dur}" {rep} values="{anim_values(back_vals)}"/></rect>')
        doc.b(f'<polygon fill="url(#side{i})" points="{quad_vals[0]}">'
              f'<animate attributeName="points" dur="{dur}" {rep} values="{anim_values(quad_vals)}"/></polygon>')
        # darken the far part of the body, then lay a bright lip along the
        # front edge: reads as a bevelled, lit slab instead of a flat band
        doc.b(f'<rect width="{w}" height="{H}" rx="{RADIUS}" fill="#000" fill-opacity="{0.3 if lime else 0.5}" transform="translate({back_vals[0]})">'
              f'<animateTransform attributeName="transform" type="translate" dur="{dur}" {rep} values="{anim_values(back_vals)}"/></rect>')
        doc.b(f'<rect width="{w}" height="{H}" rx="{RADIUS}" fill="url(#side{i})" transform="translate({lip_vals[0]})">'
              f'<animateTransform attributeName="transform" type="translate" dur="{dur}" {rep} values="{anim_values(lip_vals)}"/></rect>')

        # front face
        if lime:
            doc.b(f'<rect width="{w}" height="{H}" rx="{RADIUS}" fill="url(#faceL)"/>')
        else:
            doc.b(f'<rect width="{w}" height="{H}" rx="{RADIUS}" fill="url(#faceD)"/>')
            doc.b(f'<rect width="{w}" height="{H}" rx="{RADIUS}" fill="url(#holoTint)"/>')
            doc.b(f'<rect x="0.5" y="0.5" width="{w - 1}" height="{H - 1}" rx="{RADIUS - .5}" fill="none" stroke="{HAIR}"/>')
        # top bevel highlight
        doc.b(f'<path d="M{RADIUS} 1.2H{w - RADIUS}" stroke="#fff" stroke-opacity="{0.55 if lime else 0.12}" stroke-width="1.2" stroke-linecap="round"/>')

        # sheen sweep, clipped to the face
        sw_start = 2.3 + i * 0.22
        sw_len = 1.15
        k0, k1 = sw_start / PERIOD, (sw_start + sw_len) / PERIOD
        doc.b(f'<g clip-path="url(#face{i})"><g>'
              f'<animateTransform attributeName="transform" type="translate" dur="{dur}" {rep} '
              f'keyTimes="0;{f(k0, 4)};{f(k1, 4)};1" values="-130 0;-130 0;{w + 60} 0;{w + 60} 0" '
              f'calcMode="spline" keySplines="0 0 1 1;0.45 0 0.55 1;0 0 1 1"/>'
              f'<rect x="0" y="-40" width="70" height="{H + 80}" fill="url(#{"sheenInk" if lime else "sheenG"})" transform="skewX(-22)"/>'
              f'</g></g>')

        # tag + icon
        tag_col = "#0b0b0c" if lime else MUTED
        tag_op = ' fill-opacity="0.62"' if lime else ""
        doc.b(f'<text x="{PAD}" y="31" font-family="{MONO}" font-size="14" letter-spacing="1" fill="{tag_col}"{tag_op}>{c["tag"]}</text>')
        if not lime:
            doc.b(f'<circle cx="{PAD + 26}" cy="26.6" r="3" fill="{LIME}"/>')
        else:
            doc.b(f'<circle cx="{PAD + 26}" cy="26.6" r="3" fill="{INK}"/>')
        doc.b(icon_svg(c["icon"], w - PAD - 19, 17, INK if lime else LIME))

        # odometer value
        digit_fill = INK if lime else "url(#digitG)"
        doc.b(f'<g mask="url(#drum{i})" font-family="{SANS}" font-weight="800" font-size="{f(VAL_FS)}" letter-spacing="-1">')
        start = 0.2 + i * 0.16
        out_start = ODO_PERIOD - 1.05 + i * 0.16
        ncols = len(c["digits"])
        for j, ch in enumerate(c["digits"]):
            target = int(ch)
            steps = 6 + 4 * j + (2 if i % 2 else 0)
            seq = [str((target - steps + 1 + s) % 10) for s in range(steps)]
            col_x = PAD + (j + 0.5) * COL_W
            dur_roll = 1.05 + 0.32 * j
            kts, vals, spl = odometer_column(len(seq), start, dur_roll,
                                             out_start + j * 0.05, 0.42)
            rows = "".join(
                f'<text x="{f(col_x)}" y="{f(VAL_BASE + (r + 1) * LINE_H)}">{s}</text>'
                for r, s in enumerate(seq))
            doc.b(f'<g fill="{digit_fill}" text-anchor="middle" transform="translate(0 {f(-len(seq) * LINE_H)})">'
                  f'<animateTransform attributeName="transform" type="translate" dur="{f(ODO_PERIOD)}s" {rep} '
                  f'calcMode="spline" keyTimes="{kt_list(kts)}" values="{vals}" keySplines="{spl}"/>'
                  f'{rows}</g>')
        doc.b('</g>')  # close digit mask group
        if c["suffix"]:
            sx_ = PAD + ncols * COL_W + 2
            last_land = start + 1.05 + 0.32 * (ncols - 1)
            t_in0, t_in1 = last_land - 0.12, last_land + 0.38
            # roll out exactly like the last digit column (same start, length
            # and ease-in), one full row up through the masked window, so the
            # number leaves as one unit instead of the suffix floating free
            t_out0 = out_start + (ncols - 1) * 0.05
            t_out1 = t_out0 + 0.42
            kts = kt_list([0, t_in0 / ODO_PERIOD, t_in1 / ODO_PERIOD,
                           t_out0 / ODO_PERIOD, t_out1 / ODO_PERIOD, 1])
            spl = "0 0 1 1;0.2 0.7 0.3 1;0 0 1 1;0.55 0 0.75 0.35;0 0 1 1"
            suf_fill = INK if lime else LIME
            doc.b(f'<g mask="url(#suf{i})">'
                  f'<g font-family="{SANS}" font-weight="800" font-size="{f(VAL_FS)}" '
                  f'letter-spacing="-1" fill="{suf_fill}">'
                  f'<animate attributeName="opacity" dur="{f(ODO_PERIOD)}s" {rep} calcMode="spline" '
                  f'keyTimes="{kts}" values="0;0;1;1;1;0" keySplines="{spl}"/>'
                  f'<animateTransform attributeName="transform" type="translate" dur="{f(ODO_PERIOD)}s" {rep} '
                  f'calcMode="spline" keyTimes="{kts}" values="-14 0;-14 0;0 0;0 0;0 {f(-LINE_H)};0 {f(-LINE_H)}" '
                  f'keySplines="{spl}"/>'
                  f'<text x="{f(sx_)}" y="{f(VAL_BASE)}">{c["suffix"]}</text></g></g>')

        # label
        lab_fs = LABEL_FS
        lw = min(text_w(c["label"], lab_fs), w - 2 * PAD)
        lab_col = INK if lime else "#a3a3a9"
        lab_op = ' fill-opacity="0.78"' if lime else ""
        doc.b(f'<text x="{PAD}" y="{f(LABEL_BASE)}" font-family="{SANS}" font-size="{lab_fs}" font-weight="500" '
              f'fill="{lab_col}"{lab_op} textLength="{f(lw)}" lengthAdjust="spacingAndGlyphs">{c["label"]}</text>')

        doc.b('</g>')

    doc.b('</g>')
    # outer hairline
    doc.b(f'<rect x="0.5" y="0.5" width="{VW - 1}" height="{VH - 1}" rx="21.5" fill="none" stroke="{HAIR}"/>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{VW}" height="{VH}" '
           f'viewBox="0 0 {VW} {VH}" role="img" aria-label="stats: 13 react native apps, '
           f'5 on google play, 10K+ downloads on virtual live, shipping since 2022">\n'
           f'<title>stats</title>\n<defs>\n' + "\n".join(doc.defs) + '\n</defs>\n'
           + "\n".join(doc.body) + '\n</svg>\n')
    return svg


def main():
    svg = build()
    ET.fromstring(svg)  # validate XML
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {os.path.normpath(OUT)} ({len(svg.encode('utf-8')) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
