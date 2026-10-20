#!/usr/bin/env python3
"""Generate assets/stack.svg: a 3D tech orbit for the zqh7y profile README.

Deterministic, stdlib only. Run:  python3 src/stack.py

What it draws
-------------
* a holographic wireframe globe (the "core") spinning on a tilted axis,
* a second, inner ring tilted the other way with two glowing orbs,
* nine tech tags (pills) riding a tilted 3D ring around the core.

How the "3D" works
------------------
Everything is real geometry pushed through one camera: world points are
rotated by the camera elevation (we look slightly down on the ring) and then
perspective-projected (the globe uses an orthographic projection, which is
indistinguishable at its size and keeps its silhouette an exact circle).
Positions are sampled N times per loop and played back with SMIL `values`
lists (linear interpolation between samples, the last sample equals the
first, so every loop is seamless).

Depth cues for the tags:
  * scale = perspective scale at the tag's 3D position,
  * a fog layer (ink coloured, opacity rises with depth) dims far tags while
    keeping the pill opaque, so the ring track never shows through,
  * z-order: every tag exists twice. The back copy is drawn before the core,
    the front copy after it, and a discrete SMIL `visibility` animation shows
    exactly one of them. The swap happens when the tag crosses the depth
    plane of the core (the far left / right of the ring), well away from the
    globe, so the switch is invisible -- but tags really pass behind it.
  * the tag passing the front of the ring lights up acid lime: a clip wipe
    with a bright scan line fills it from its leading edge and drains it as
    it leaves (no muddy crossfade), and the "01 / 09" counter top-right
    follows whichever tag owns the front.

Every loop length divides 24 s (ring 24, globe 12, meridians 1, orbs 8,
ping 4, front hand-off 24/9), so the whole image repeats every 24 s.

Globe: latitude circles are invariant under the spin, so they are static
paths split into short pieces whose opacity follows their depth. Meridians
are animated: six great circles = twelve half meridians 30 deg apart, so the
picture repeats after 30 deg of spin and the meridian animation only needs to
cover that (short loop, tiny file). Each meridian is cut into 30 deg latitude
bands (one quadratic Bezier each -- exact for a projected circular arc to
well under a pixel) with their own depth-driven opacity.
"""
import math
import os
import random
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "assets", "stack.svg"))

# ---------------------------------------------------------------- palette
INK = "#0b0b0c"
PANEL = "#141416"
HAIR = "#26262b"
TEXT = "#f5f5f2"
MUTED = "#8a8a90"
LIME = "#d4ff3a"
LIME2 = "#b8f000"
CYAN = "#7af0ff"
VIOLET = "#b48cff"
PINK = "#ff8ad8"

SANS = "'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

# ---------------------------------------------------------------- canvas / camera
VW, VH = 1000, 280
T = 24.0                 # seconds: one full revolution of the tag ring
N = 72                   # samples per revolution (5 deg)
CX, CY = 500.0, 146.0    # screen position of the world origin (the core)
ELEV = math.radians(11.0)  # camera looks down on the ring by this much
D = 4.1                  # camera distance (ring radius = 1)
RING_PX = 388.0          # half width of the ring at the depth of the core
F = RING_PX * D          # focal length in px

# ---------------------------------------------------------------- tags
TAGS = [
    ("React Native", "react", CYAN),
    ("Expo", "expo", VIOLET),
    ("JavaScript", "js", LIME),
    ("Python", "python", PINK),
    ("Flask", "flask", CYAN),
    ("PostgreSQL", "pg", VIOLET),
    ("Three.js", "three", LIME),
    ("Luau", "luau", PINK),
    ("OpenCV", "opencv", CYAN),
]
PILL_H = 35.0
PILL_FS = 16.5
PILL_PADL = 13.0
ICON_BOX = 16.0
ICON_GAP = 9.0
PILL_PADR = 16.0
FRONT_DEG = -90.0        # theta of the point of the ring nearest the camera
HL_HOLD = 15.0           # tag is fully lit within this many degrees of the front
HL_EDGE = 20.0           # ... and dark beyond this (half the tag spacing: clean hand-off)

# ---------------------------------------------------------------- globe
GR = 74.0                # globe radius px
G_SPIN_T = 12.0          # seconds per full spin
G_ROLL = math.radians(-18.0)   # axis leans right on screen
G_PITCH = math.radians(8.0)    # extra tilt of the north pole toward camera
MERID = 12               # half meridians (6 great circles)
MER_STEP = 360.0 / MERID
MER_FRAMES = 10          # samples across one 30 deg symmetry period
LATS = (-60, -30, 0, 30, 60)

# ---------------------------------------------------------------- inner ring
IR = 0.29                # inner ring radius (world units)
IR_ROLL = math.radians(22.0)
IR_DASH = (3.0, 5.0)
IR_PITCH = math.radians(20.0)
ORB_T = 8.0
ORB_N = 64

# ---------------------------------------------------------------- ripple
RIP_T = 4.0              # a ping leaves the core every RIP_T seconds
RIP_R = (0.2, 1.06)      # radius range (world units) of the ping in the ring plane
RIP_FRAMES = 14
RIP_ACTIVE = 0.8         # fraction of RIP_T the ping is visible

# Arial Bold advance widths (em). Used with textLength so every fallback
# font lands on the same width.
_WB = {
    " ": .278, ".": .278, "a": .556, "b": .611, "c": .556, "d": .611,
    "e": .556, "f": .333, "g": .611, "h": .611, "i": .278, "j": .278,
    "k": .556, "l": .278, "m": .889, "n": .611, "o": .611, "p": .611,
    "q": .611, "r": .389, "s": .556, "t": .333, "u": .611, "v": .556,
    "w": .778, "x": .556, "y": .556, "z": .5,
    "A": .722, "B": .722, "C": .722, "D": .722, "E": .667, "F": .611,
    "G": .778, "H": .722, "I": .278, "J": .556, "K": .722, "L": .611,
    "M": .833, "N": .722, "O": .778, "P": .667, "Q": .778, "R": .722,
    "S": .667, "T": .611, "U": .722, "V": .667, "W": .944, "X": .667,
    "Y": .667, "Z": .611,
}
_WR = {
    " ": .278, "·": .278, "a": .556, "b": .556, "c": .5, "d": .556,
    "e": .556, "f": .278, "g": .556, "h": .556, "i": .222, "j": .222,
    "k": .5, "l": .222, "m": .833, "n": .556, "o": .556, "p": .556,
    "q": .556, "r": .333, "s": .5, "t": .278, "u": .556, "v": .5, "w": .722,
    "x": .5, "y": .5, "z": .5,
}


def text_w(s, fs, bold=False):
    tbl = _WB if bold else _WR
    return sum(tbl.get(ch, .6) for ch in s) * fs


# ---------------------------------------------------------------- helpers
def f(x, nd=1):
    """Compact number formatting."""
    s = f"{x:.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    if s in ("-0", "", "-"):
        s = "0"
    return s


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def smooth(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def rot_x(p, a):
    x, y, z = p
    c, s = math.cos(a), math.sin(a)
    return (x, y * c + z * s, -y * s + z * c)


def rot_z(p, a):
    x, y, z = p
    c, s = math.cos(a), math.sin(a)
    return (x * c - y * s, x * s + y * c, z)


def cam(p):
    """World -> camera. +z is away from the viewer; far side goes up."""
    return rot_x(p, ELEV)


def project(p):
    """Camera-space point -> (X, Y, perspective scale rel. to core, z)."""
    x, y, z = p
    k = F / (D + z)
    return CX + x * k, CY - y * k, D / (D + z), z


def ring_point(theta_deg):
    t = math.radians(theta_deg)
    return project(cam((math.cos(t), 0.0, math.sin(t))))


def discrete_vis(intervals_visible, period):
    """SMIL discrete visibility animation.

    intervals_visible: list of (start, end) fractions in [0, 1) (end may wrap)
    during which the element is visible.
    """
    # build a boolean timeline from breakpoints
    pts = set([0.0])
    for a, b in intervals_visible:
        pts.add(a % 1.0)
        pts.add(b % 1.0)
    pts = sorted(pts)

    def vis_at(u):
        for a, b in intervals_visible:
            a %= 1.0
            b %= 1.0
            if a < b:
                if a <= u < b:
                    return True
            else:
                if u >= a or u < b:
                    return True
        return False

    vals, kts = [], []
    for p in pts:
        v = "visible" if vis_at(p + 1e-9) else "hidden"
        if vals and vals[-1] == v:
            continue
        vals.append(v)
        kts.append(p)
    first = vals[0]
    return first, (f'<animate attributeName="visibility" calcMode="discrete" dur="{f(period)}s" '
                   f'repeatCount="indefinite" values="{";".join(vals)}" '
                   f'keyTimes="{";".join(f(k, 5) for k in kts)}"/>')


def periodic_pl(points):
    """Periodic piecewise-linear function given by (u, v) breakpoints (u any
    real, period 1) -> (keyTimes, values) covering [0, 1] exactly."""
    pts = sorted(((u % 1.0), v) for u, v in points)

    def val(u):
        ext = [(a - 1.0, v) for a, v in pts] + pts + [(a + 1.0, v) for a, v in pts]
        for (a0, v0), (a1, v1) in zip(ext, ext[1:]):
            if a0 <= u <= a1:
                return v0 if a1 == a0 else lerp(v0, v1, (u - a0) / (a1 - a0))
        raise ValueError(u)

    kts = [0.0] + [u for u, _ in pts if 1e-9 < u < 1 - 1e-9] + [1.0]
    vals = [val(0.0)] + [v for u, v in pts if 1e-9 < u < 1 - 1e-9] + [val(0.0)]
    return kts, vals


class Doc:
    def __init__(self):
        self.defs = []
        self.body = []

    def d(self, s):
        self.defs.append(s)

    def b(self, s):
        self.body.append(s)


# ---------------------------------------------------------------- icons
def icon_markup(kind):
    """Stroke icons in a ~16px box centred on 0,0 drawn with currentColor."""
    sw = 'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'
    if kind == "react":
        e = '<ellipse rx="7.8" ry="3"{}/>'
        return (f'<g {sw}>' + e.format("") + e.format(' transform="rotate(60)"')
                + e.format(' transform="rotate(120)"') + '</g>'
                '<circle r="1.7" fill="currentColor"/>')
    if kind == "expo":
        return (f'<path {sw} d="M-7.6 6.4L-1.5 -5.4Q0 -8 1.5 -5.4L7.6 6.4"/>'
                f'<path {sw} d="M-3.4 6.4L0 0.4L3.4 6.4"/>')
    if kind == "js":
        return (f'<path {sw} d="M-2.6 -7.2Q-5.8 -7.2 -5.8 -4.4V-1.6Q-5.8 0 -7.6 0Q-5.8 0 -5.8 1.6'
                f'V4.4Q-5.8 7.2 -2.6 7.2M2.6 -7.2Q5.8 -7.2 5.8 -4.4V-1.6Q5.8 0 7.6 0Q5.8 0 5.8 1.6'
                f'V4.4Q5.8 7.2 2.6 7.2"/>')
    if kind == "python":
        return (f'<g {sw}><rect x="-7.4" y="-7.4" width="9.6" height="9.6" rx="3"/>'
                f'<rect x="-2.2" y="-2.2" width="9.6" height="9.6" rx="3"/></g>'
                '<circle cx="-4.6" cy="-4.6" r="1.1" fill="currentColor"/>'
                '<circle cx="4.6" cy="4.6" r="1.1" fill="currentColor"/>')
    if kind == "flask":
        return (f'<path {sw} d="M-3 -7.4H3M-1.6 -7.4V-2.2L-6.6 5.6Q-7.4 7.4 -5.4 7.4H5.4'
                f'Q7.4 7.4 6.6 5.6L1.6 -2.2V-7.4"/>'
                f'<path {sw} d="M-4.4 2.6H4.4"/>')
    if kind == "pg":
        return (f'<g {sw}><ellipse cy="-4.6" rx="6.6" ry="2.6"/>'
                f'<path d="M-6.6 -4.6V4.6A6.6 2.6 0 0 0 6.6 4.6V-4.6M-6.6 0A6.6 2.6 0 0 0 6.6 0"/></g>')
    if kind == "three":
        return (f'<path {sw} d="M0 -7.4L7.8 6.6H-7.8ZM-3.9 -.4H3.9L0 6.6Z"/>')
    if kind == "luau":
        return (f'<g transform="rotate(16)"><rect {sw} x="-6.4" y="-6.4" width="12.8" height="12.8" rx="1.6"/>'
                '<rect x="0.6" y="-4.4" width="3.8" height="3.8" fill="currentColor"/></g>')
    if kind == "opencv":
        return (f'<g {sw}><circle cy="-4" r="3.1"/><circle cx="-4.4" cy="3.6" r="3.1"/>'
                f'<circle cx="4.4" cy="3.6" r="3.1"/></g>')
    raise ValueError(kind)


# ---------------------------------------------------------------- build
def build():
    doc = Doc()
    rnd = random.Random(7)

    # ------------------------------------------------ defs: global gradients
    doc.d(f'''<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#101012"/><stop offset="1" stop-color="{INK}"/>
</linearGradient>
<pattern id="dots" width="20" height="20" patternUnits="userSpaceOnUse">
  <circle cx="1" cy="1" r="1" fill="#ffffff" fill-opacity="0.045"/>
</pattern>
<clipPath id="frame"><rect width="{VW}" height="{VH}" rx="22"/></clipPath>
<radialGradient id="halo" cx="0.5" cy="0.5" r="0.5">
  <stop offset="0" stop-color="{VIOLET}" stop-opacity="0.34"/>
  <stop offset="0.38" stop-color="{CYAN}" stop-opacity="0.12"/>
  <stop offset="0.7" stop-color="{PINK}" stop-opacity="0.04"/>
  <stop offset="1" stop-color="{PINK}" stop-opacity="0"/>
</radialGradient>
<radialGradient id="limeGlow" cx="0.5" cy="0.5" r="0.5">
  <stop offset="0" stop-color="{LIME}" stop-opacity="0.22"/>
  <stop offset="0.6" stop-color="{LIME}" stop-opacity="0.05"/>
  <stop offset="1" stop-color="{LIME}" stop-opacity="0"/>
</radialGradient>
<radialGradient id="globeFill" cx="0.42" cy="0.36" r="0.68">
  <stop offset="0" stop-color="#22193a"/>
  <stop offset="0.55" stop-color="#121019"/>
  <stop offset="1" stop-color="#0a0a0d"/>
</radialGradient>
<radialGradient id="atmo" cx="0.5" cy="0.5" r="0.5">
  <stop offset="{f(GR / (GR + 18) - 0.01, 3)}" stop-color="{VIOLET}" stop-opacity="0"/>
  <stop offset="{f(GR / (GR + 18) + 0.005, 3)}" stop-color="{VIOLET}" stop-opacity="0.42"/>
  <stop offset="{f((GR + 6) / (GR + 18), 3)}" stop-color="{CYAN}" stop-opacity="0.12"/>
  <stop offset="1" stop-color="{CYAN}" stop-opacity="0"/>
</radialGradient>
<radialGradient id="spec" cx="0.5" cy="0.5" r="0.5">
  <stop offset="0" stop-color="#ffffff" stop-opacity="0.28"/>
  <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
</radialGradient>
<linearGradient id="holoG" gradientUnits="userSpaceOnUse" x1="{f(CX - GR)}" y1="{f(CY - GR)}" x2="{f(CX + GR)}" y2="{f(CY + GR)}">
  <stop offset="0" stop-color="{CYAN}"/><stop offset="0.5" stop-color="{VIOLET}"/><stop offset="1" stop-color="{PINK}"/>
</linearGradient>
<linearGradient id="rimG" gradientUnits="userSpaceOnUse" x1="{f(CX - GR)}" y1="{f(CY - GR)}" x2="{f(CX + GR)}" y2="{f(CY + GR)}">
  <stop offset="0" stop-color="{CYAN}"/><stop offset="0.45" stop-color="{VIOLET}"/>
  <stop offset="0.8" stop-color="{PINK}"/><stop offset="1" stop-color="{LIME}"/>
</linearGradient>
<linearGradient id="trackG" gradientUnits="userSpaceOnUse" x1="{f(CX - RING_PX)}" y1="0" x2="{f(CX + RING_PX)}" y2="0">
  <stop offset="0" stop-color="{CYAN}"/><stop offset="0.5" stop-color="{VIOLET}"/><stop offset="1" stop-color="{PINK}"/>
</linearGradient>
<linearGradient id="pillFill" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#1e1e23"/><stop offset="1" stop-color="{PANEL}"/>
</linearGradient>
<linearGradient id="pillStroke" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{CYAN}"/><stop offset="0.5" stop-color="{VIOLET}"/><stop offset="1" stop-color="{PINK}"/>
</linearGradient>
<linearGradient id="sheen" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.5" stop-color="#fff" stop-opacity="0.75"/>
  <stop offset="1" stop-color="#fff" stop-opacity="0"/>
</linearGradient>
<linearGradient id="scanG" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{LIME}" stop-opacity="0"/><stop offset="0.5" stop-color="{LIME}" stop-opacity="0.75"/>
  <stop offset="1" stop-color="{LIME}" stop-opacity="0"/>
</linearGradient>
<linearGradient id="limeFill" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#e4ff7a"/><stop offset="0.55" stop-color="{LIME}"/><stop offset="1" stop-color="{LIME2}"/>
</linearGradient>''')

    # ------------------------------------------------ background
    doc.b(f'<rect width="{VW}" height="{VH}" rx="22" fill="url(#bg)"/>')
    doc.b('<g clip-path="url(#frame)">')
    doc.b(f'<rect width="{VW}" height="{VH}" fill="url(#dots)"/>')

    # stars (deterministic), gentle twinkle with periods dividing T
    stars = []
    for _ in range(26):
        x = rnd.uniform(20, VW - 20)
        y = rnd.uniform(14, VH - 14)
        if abs(x - CX) < 140 and abs(y - CY) < 110:
            continue
        stars.append((x, y, rnd.choice((0.8, 1.0, 1.2)), rnd.choice((3, 4, 6, 8)),
                      rnd.choice((CYAN, VIOLET, PINK, "#ffffff", "#ffffff"))))
    for x, y, r, per, col in stars:
        a, b = (0.15, 0.7) if rnd.random() < 0.5 else (0.7, 0.15)
        doc.b(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{col}" opacity="{f(a, 2)}">'
              f'<animate attributeName="opacity" values="{f(a, 2)};{f(b, 2)};{f(a, 2)}" dur="{per}s" '
              f'repeatCount="indefinite"/></circle>')

    # big soft glow behind the core
    doc.b(f'<ellipse cx="{f(CX)}" cy="{f(CY + 4)}" rx="300" ry="150" fill="url(#halo)">'
          f'<animate attributeName="opacity" values="0.8;1;0.8" dur="6s" repeatCount="indefinite"/></ellipse>')

    # ------------------------------------------------ label (top-left)
    lab = "stack"
    lab_w = len(lab) * 16 * 0.6
    chip_w = 31 + lab_w + 15
    doc.b(f'<g transform="translate(30 24)">'
          f'<rect x="0.5" y="0.5" width="{f(chip_w)}" height="31" rx="15.5" fill="{LIME}" fill-opacity="0.06" '
          f'stroke="{LIME}" stroke-opacity="0.35"/>'
          f'<circle cx="17" cy="16" r="4" fill="{LIME}">'
          f'<animate attributeName="opacity" values="1;0.35;1" dur="2s" repeatCount="indefinite"/></circle>'
          f'<text x="31" y="21.5" font-family="{MONO}" font-size="16" fill="{LIME}" '
          f'textLength="{f(lab_w)}" lengthAdjust="spacingAndGlyphs">{lab}</text>'
          f'</g>')
    sub = "what i build with"
    sub_w = text_w(sub, 19)
    doc.b(f'<text x="32" y="83" font-family="{SANS}" font-size="19" font-weight="500" fill="{MUTED}" '
          f'textLength="{f(sub_w)}" lengthAdjust="spacingAndGlyphs">{sub}</text>')

    # top-right counter
    n_t = len(TAGS)
    cw = 16 * 0.6                        # mono advance at 16px
    right = VW - 32
    tail = f" / {n_t:02d}"
    tail_w = len(tail) * cw
    num_x = right - tail_w - 2 * cw
    doc.b(f'<text x="{f(right - tail_w)}" y="40" font-family="{MONO}" font-size="16" fill="{MUTED}" '
          f'textLength="{f(tail_w)}" lengthAdjust="spacingAndGlyphs" xml:space="preserve">{tail}</text>')
    for i in range(n_t):
        first, vis_anim = discrete_vis([(i / n_t - .5 / n_t, i / n_t + .5 / n_t)], T)
        doc.b(f'<text x="{f(num_x)}" y="40" font-family="{MONO}" font-size="16" font-weight="700" fill="{LIME}" '
              f'textLength="{f(2 * cw)}" lengthAdjust="spacingAndGlyphs" visibility="{first}">{i + 1:02d}{vis_anim}</text>')
    # progress: fills while the current tag owns the front (half a step either side)
    bw = 2 * cw + tail_w
    bx = right - bw
    doc.b(f'<rect x="{f(bx)}" y="50" width="{f(bw)}" height="3" rx="1.5" fill="{HAIR}"/>')
    doc.b(f'<rect x="{f(bx)}" y="50" width="{f(bw / 2)}" height="3" rx="1.5" fill="{LIME}">'
          f'<animate attributeName="width" dur="{f(T / n_t, 4)}s" repeatCount="indefinite" '
          f'keyTimes="0;.4999;.5;1" values="{f(bw / 2)};{f(bw)};0;{f(bw / 2)}"/></rect>')

    # ------------------------------------------------ outer ring track (static)
    def ring_path(t0, t1, step=2.0, rscale=1.0):
        pts = []
        t = t0
        while t <= t1 + 1e-9:
            tt = math.radians(t)
            X, Y, _, _ = project(cam((rscale * math.cos(tt), 0.0, rscale * math.sin(tt))))
            pts.append(f"{f(X)} {f(Y)}")
            t += step
        return "M" + "L".join(pts)

    # far half (theta 0..180), near half (180..360)
    doc.b(f'<path d="{ring_path(0, 180)}" fill="none" stroke="url(#trackG)" stroke-opacity="0.28" stroke-width="1"/>')
    doc.b(f'<path d="{ring_path(180, 360)}" fill="none" stroke="url(#trackG)" stroke-opacity="0.65" stroke-width="1.6"/>')
    # faint outer guide ring, dashed
    doc.b(f'<path d="{ring_path(0, 360, 2.0, 1.085)}" fill="none" stroke="{MUTED}" stroke-opacity="0.22" '
          f'stroke-width="1" stroke-dasharray="2 7"/>')

    # ------------------------------------------------ orbit dots between tags (single layer: never overlap core)
    n_tags = len(TAGS)
    spacing = 360.0 / n_tags
    per_tag = N // n_tags
    assert per_tag * n_tags == N

    def tag_state(theta):
        X, Y, s, z = ring_point(theta)
        zn = z / math.cos(ELEV)            # -1 front .. 1 back
        fog = 0.74 * smooth(-0.15, 1.0, zn)
        return X, Y, s, zn, fog

    for i in range(n_tags):
        th0 = FRONT_DEG + spacing * (i + 0.5)
        xs, rs, ops = [], [], []
        for k in range(N + 1):
            th = th0 - 360.0 * k / N
            X, Y, s, zn, fog = tag_state(th)
            xs.append(f"{f(X)},{f(Y)}")
            rs.append(f(2.3 * s, 2))
            ops.append(f(lerp(0.95, 0.25, (zn + 1) / 2), 2))
        doc.b(f'<g transform="translate({xs[0]})">'
              f'<animateTransform attributeName="transform" type="translate" dur="{f(T)}s" repeatCount="indefinite" values="{";".join(xs)}"/>'
              f'<circle r="{rs[0]}" fill="{LIME}" opacity="{ops[0]}">'
              f'<animate attributeName="r" dur="{f(T)}s" repeatCount="indefinite" values="{";".join(rs)}"/>'
              f'<animate attributeName="opacity" dur="{f(T)}s" repeatCount="indefinite" values="{";".join(ops)}"/>'
              f'</circle></g>')

    # lime "stage" glow where the active tag sits
    fx, fy, _, _ = ring_point(FRONT_DEG)
    doc.b(f'<ellipse cx="{f(fx)}" cy="{f(fy + 6)}" rx="190" ry="26" fill="url(#limeGlow)" opacity="0.9"/>')

    # ------------------------------------------------ tag pill definitions
    pills = []
    for i, (name, icon, col) in enumerate(TAGS):
        tw = text_w(name, PILL_FS, bold=True)
        w = PILL_PADL + ICON_BOX + ICON_GAP + tw + PILL_PADR
        h = PILL_H
        x0, y0 = -w / 2, -h / 2
        ix = x0 + PILL_PADL + ICON_BOX / 2
        tx = x0 + PILL_PADL + ICON_BOX + ICON_GAP
        ty = PILL_FS * 0.36
        pills.append(dict(w=w, h=h))
        doc.d(f'<g id="ic{i}">{icon_markup(icon)}</g>')
        doc.d(f'<clipPath id="pc{i}"><rect x="{f(x0)}" y="{f(y0)}" width="{f(w)}" height="{f(h)}" rx="{f(h / 2)}"/></clipPath>')
        # dark pill
        doc.d(f'<g id="t{i}">'
              f'<rect x="{f(x0)}" y="{f(y0)}" width="{f(w)}" height="{f(h)}" rx="{f(h / 2)}" fill="url(#pillFill)"/>'
              f'<rect x="{f(x0 + .6)}" y="{f(y0 + .6)}" width="{f(w - 1.2)}" height="{f(h - 1.2)}" rx="{f(h / 2 - .6)}" '
              f'fill="none" stroke="url(#pillStroke)" stroke-opacity="0.55" stroke-width="1.2"/>'
              f'<path d="M{f(x0 + h / 2)} {f(y0 + 1.6)}H{f(-x0 - h / 2)}" stroke="#fff" stroke-opacity="0.14" stroke-linecap="round"/>'
              f'<use xlink:href="#ic{i}" x="{f(ix)}" color="{col}"/>'
              f'<text x="{f(tx)}" y="{f(ty)}" font-family="{SANS}" font-size="{f(PILL_FS)}" font-weight="600" '
              f'fill="{TEXT}" textLength="{f(tw)}" lengthAdjust="spacingAndGlyphs">{name}</text>'
              f'</g>')
        # lit (lime) pill
        doc.d(f'<g id="L{i}">'
              f'<rect x="{f(x0 - 7)}" y="{f(y0 - 7)}" width="{f(w + 14)}" height="{f(h + 14)}" rx="{f(h / 2 + 7)}" '
              f'fill="none" stroke="{LIME}" stroke-opacity="0.07" stroke-width="5"/>'
              f'<rect x="{f(x0 - 3)}" y="{f(y0 - 3)}" width="{f(w + 6)}" height="{f(h + 6)}" rx="{f(h / 2 + 3)}" '
              f'fill="none" stroke="{LIME}" stroke-opacity="0.22" stroke-width="2"/>'
              f'<rect x="{f(x0)}" y="{f(y0)}" width="{f(w)}" height="{f(h)}" rx="{f(h / 2)}" fill="url(#limeFill)"/>'
              f'<path d="M{f(x0 + h / 2)} {f(y0 + 1.6)}H{f(-x0 - h / 2)}" stroke="#fff" stroke-opacity="0.6" stroke-linecap="round"/>'
              f'<use xlink:href="#ic{i}" x="{f(ix)}" color="{INK}"/>'
              f'<text x="{f(tx)}" y="{f(ty)}" font-family="{SANS}" font-size="{f(PILL_FS)}" font-weight="700" '
              f'fill="{INK}" textLength="{f(tw)}" lengthAdjust="spacingAndGlyphs">{name}</text>'
              f'</g>')

    # per-tag sampled motion (shared shape, baked phase per tag)
    tag_anim = []
    for i in range(n_tags):
        th0 = FRONT_DEG + spacing * i
        tr, sc, fg = [], [], []
        raw = []
        for k in range(N + 1):
            th = th0 - 360.0 * k / N
            X, Y, s, zn, fog = tag_state(th)
            tr.append(f"{f(X)},{f(Y)}")
            sc.append(f(s, 3))
            fg.append(f(fog, 2))
            raw.append((X, Y, s, zn))
        # visible-in-back interval: theta in (0, 180) -> fraction of loop
        a = ((th0 - 180.0) / 360.0) % 1.0
        b = (th0 / 360.0) % 1.0
        uc = i / n_tags                      # loop fraction when this tag is dead front
        e, hh = HL_EDGE / 360.0, HL_HOLD / 360.0
        # lime state arrives as a wipe (no muddy crossfade): a clip rect in pill
        # space grows from the leading (left) edge, holds, then recedes to the
        # right while the tag leaves. Its x slides back while its width is 0.
        pw = pills[i]["w"]
        xa, wa = -pw / 2 - 10, pw + 20
        wk, wv = periodic_pl([(uc - e, 0.0), (uc - hh, wa), (uc + hh, wa), (uc + e, 0.0)])
        xk, xv = periodic_pl([(uc - e, xa), (uc + hh, xa), (uc + e, xa + wa)])
        ph_ = pills[i]["h"]
        doc.d(f'<clipPath id="wc{i}"><rect x="{f(xv[0])}" y="{f(-ph_ / 2 - 12)}" width="{f(wv[0])}" height="{f(ph_ + 24)}">'
              f'<animate attributeName="x" dur="{f(T)}s" repeatCount="indefinite" '
              f'keyTimes="{";".join(f(k, 5) for k in xk)}" values="{";".join(f(v) for v in xv)}"/>'
              f'<animate attributeName="width" dur="{f(T)}s" repeatCount="indefinite" '
              f'keyTimes="{";".join(f(k, 5) for k in wk)}" values="{";".join(f(v) for v in wv)}"/>'
              f'</rect></clipPath>')
        # bright scan line riding the moving edge of the wipe (only while wiping)
        eps = 0.0005
        ek, ev = periodic_pl([(uc - e, xa), (uc - hh, xa + wa), (uc + hh - eps, xa + wa),
                              (uc + hh, xa), (uc + e, xa + wa)])
        ok, ov = periodic_pl([(uc - e - eps, 0), (uc - e, 1), (uc - hh, 1), (uc - hh + eps, 0),
                              (uc + hh - eps, 0), (uc + hh, 1), (uc + e, 1), (uc + e + eps, 0)])
        tag_anim.append(dict(tr=tr, sc=sc, fg=fg, back=(a, b), raw=raw,
                             edge=(ek, ev, ok, ov)))

    # sanity: no two tags in the same layer overlap at any sample
    for k in range(N):
        boxes = []
        for i in range(n_tags):
            X, Y, s, zn = tag_anim[i]["raw"][k]
            boxes.append((X, Y, pills[i]["w"] * s / 2 + 2, pills[i]["h"] * s / 2 + 2, zn > 0))
        for i in range(n_tags):
            for j in range(i + 1, n_tags):
                bi, bj = boxes[i], boxes[j]
                if bi[4] != bj[4]:
                    continue
                if abs(bi[0] - bj[0]) < bi[2] + bj[2] and abs(bi[1] - bj[1]) < bi[3] + bj[3]:
                    print(f"warn: overlap tags {i},{j} at sample {k}")
    # bounds
    ys = [(r[1] - PILL_H * r[2] / 2, r[1] + PILL_H * r[2] / 2) for a in tag_anim for r in a["raw"]]
    xs_ = [(r[0] - pills[i]["w"] * r[2] / 2, r[0] + pills[i]["w"] * r[2] / 2)
           for i, a in enumerate(tag_anim) for r in a["raw"]]
    print(f"tag bounds x {min(x for x, _ in xs_):.0f}..{max(x for _, x in xs_):.0f} "
          f"y {min(y for y, _ in ys):.0f}..{max(y for _, y in ys):.0f}")

    def tag_instance(i, front):
        A = tag_anim[i]
        p = pills[i]
        a, b = A["back"]
        vis = [(b, a)] if front else [(a, b)]
        first, vis_anim = discrete_vis(vis, T)
        out = [f'<g visibility="{first}">{vis_anim}',
               f'<g transform="translate({A["tr"][0]})">'
               f'<animateTransform attributeName="transform" type="translate" dur="{f(T)}s" repeatCount="indefinite" values="{";".join(A["tr"])}"/>',
               f'<g transform="scale({A["sc"][0]})">'
               f'<animateTransform attributeName="transform" type="scale" dur="{f(T)}s" repeatCount="indefinite" values="{";".join(A["sc"])}"/>',
               f'<use xlink:href="#t{i}"/>']
        w, h = p["w"], p["h"]
        if front:
            # sheen sweeps across the lit pill right as it reaches the front.
            # Every tag is dead front at a multiple of T/9, so one short loop fits all.
            sx0, sx1 = -w / 2 - 40, w / 2 + 14
            out.append(f'<g clip-path="url(#wc{i})"><use xlink:href="#L{i}"/>'
                       f'<g clip-path="url(#pc{i})"><g transform="translate({f(sx0)} 0)">'
                       f'<animateTransform attributeName="transform" type="translate" '
                       f'dur="{f(T / n_tags, 4)}s" repeatCount="indefinite" keyTimes="0;.06;.36;1" '
                       f'values="{f(sx0)} 0;{f(sx0)} 0;{f(sx1)} 0;{f(sx1)} 0"/>'
                       f'<rect x="0" y="{f(-h / 2 - 4)}" width="24" height="{f(h + 8)}" '
                       f'fill="url(#sheen)" transform="skewX(-22)"/></g></g></g>')
            ek, ev, ok, ov = A["edge"]
            out.append(f'<g clip-path="url(#pc{i})" opacity="{f(ov[0])}">'
                       f'<animate attributeName="opacity" dur="{f(T)}s" repeatCount="indefinite" '
                       f'keyTimes="{";".join(f(k, 5) for k in ok)}" values="{";".join(f(v) for v in ov)}"/>'
                       f'<g transform="translate({f(ev[0])} 0)">'
                       f'<animateTransform attributeName="transform" type="translate" dur="{f(T)}s" repeatCount="indefinite" '
                       f'keyTimes="{";".join(f(k, 5) for k in ek)}" values="{";".join(f(v) + " 0" for v in ev)}"/>'
                       f'<rect x="-9" y="{f(-h / 2)}" width="18" height="{f(h)}" fill="url(#scanG)"/>'
                       f'<rect x="-1.1" y="{f(-h / 2)}" width="2.2" height="{f(h)}" fill="#fbffe6"/>'
                       f'</g></g>')
        out.append(f'<rect x="{f(-w / 2 - .5)}" y="{f(-h / 2 - .5)}" width="{f(w + 1)}" height="{f(h + 1)}" '
                   f'rx="{f(h / 2 + .5)}" fill="{INK}" opacity="{A["fg"][0]}">'
                   f'<animate attributeName="opacity" dur="{f(T)}s" repeatCount="indefinite" values="{";".join(A["fg"])}"/></rect>')
        out.append('</g></g></g>')
        return "".join(out)

    # ------------------------------------------------ back layer tags
    doc.b('<g id="back">')
    for i in range(n_tags):
        doc.b(tag_instance(i, False))
    doc.b('</g>')

    # ------------------------------------------------ ping ripple in the ring plane
    def ripple_half(r, far, step=6.0):
        t0 = 0.0 if far else 180.0
        pts = []
        for j in range(int(180 / step) + 1):
            tt = math.radians(t0 + j * step)
            X, Y, _, _ = project(cam((r * math.cos(tt), 0.0, r * math.sin(tt))))
            pts.append(f"{f(X)} {f(Y)}")
        return "M" + "L".join(pts)

    def ripple(far):
        ds, ops, kts = [], [], []
        for k in range(RIP_FRAMES + 1):
            u = k / RIP_FRAMES
            e = 1 - (1 - u) ** 2                  # ease-out
            ds.append(ripple_half(lerp(RIP_R[0], RIP_R[1], e), far))
            ops.append(f(0.55 * (1 - u) ** 1.3 * smooth(0.0, 0.12, u), 2))
            kts.append(f(u * RIP_ACTIVE, 4))
        ds.append(ds[0])
        ops.append("0")
        kts.append("1")
        return (f'<path d="{ds[0]}" fill="none" stroke="{LIME}" stroke-width="{1.0 if far else 1.4}" '
                f'opacity="0"><animate attributeName="d" dur="{f(RIP_T)}s" repeatCount="indefinite" '
                f'keyTimes="{";".join(kts)}" values="{";".join(ds)}"/>'
                f'<animate attributeName="opacity" dur="{f(RIP_T)}s" repeatCount="indefinite" '
                f'keyTimes="{";".join(kts)}" values="{";".join(ops)}"/></path>')

    doc.b(f'<g opacity="0.55">{ripple(True)}</g>')

    # ------------------------------------------------ inner ring (tilted the other way)
    def inner_cam(theta_deg, r=IR):
        t = math.radians(theta_deg)
        p = (r * math.cos(t), 0.0, r * math.sin(t))
        p = rot_x(p, IR_PITCH)
        p = rot_z(p, IR_ROLL)
        return cam(p)

    def inner_arcs(step=2.0):
        """Split inner ring into far (z>0) and near (z<=0) polylines."""
        samples = []
        t = 0.0
        while t < 360.0 - 1e-9:
            samples.append(t)
            t += step
        zs = [inner_cam(t)[2] for t in samples]
        # rotate so we start right after a sign change into 'far'
        n = len(samples)
        start = next(j for j in range(n) if zs[j] > 0 and zs[j - 1] <= 0)
        runs = {True: [], False: []}
        cur, cur_far = [], None
        for jj in range(n + 1):
            j = (start + jj) % n
            far = zs[j] > 0
            X, Y, _, _ = project(inner_cam(samples[j]))
            if cur_far is None or far == cur_far:
                cur.append((X, Y))
                cur_far = far
            else:
                cur.append((X, Y))   # share the joint
                runs[cur_far].append(cur)
                cur, cur_far = [(X, Y)], far
        if len(cur) > 1:
            runs[cur_far].append(cur)
        return runs

    iarcs = inner_arcs()

    def poly(pts):
        return "M" + "L".join(f"{f(x)} {f(y)}" for x, y in pts)

    def plen(pts):
        return sum(math.hypot(x1 - x0, y1 - y0) for (x0, y0), (x1, y1) in zip(pts, pts[1:]))

    dash_p = sum(IR_DASH)
    ring_len = sum(plen(r) for k in (True, False) for r in iarcs[k])
    crawl = round(ring_len / dash_p) * dash_p      # one lap per orb period, whole dashes

    def dashed(run, base, op, sw):
        # orbs travel against the path direction -> offset grows
        o0 = -base % dash_p
        return (f'<path d="{poly(run)}" fill="none" stroke="{LIME}" stroke-opacity="{op}" stroke-width="{sw}" '
                f'stroke-dasharray="{f(IR_DASH[0])} {f(IR_DASH[1])}" stroke-dashoffset="{f(o0, 2)}">'
                f'<animate attributeName="stroke-dashoffset" dur="{f(ORB_T)}s" repeatCount="indefinite" '
                f'values="{f(o0, 2)};{f(o0 + crawl, 2)}"/></path>')

    far_run = iarcs[True][0]
    near_run = iarcs[False][0]
    assert len(iarcs[True]) == 1 and len(iarcs[False]) == 1
    doc.b(dashed(far_run, 0.0, 0.22, 1))

    # orbs on the inner ring
    orbs = [(0.0, LIME, 3.4), (180.0, CYAN, 2.8)]
    orb_layers = {True: [], False: []}
    for o_i, (ph, col, rad) in enumerate(orbs):
        tr, rs, far_flags = [], [], []
        for k in range(ORB_N + 1):
            th = ph - 360.0 * k / ORB_N
            X, Y, s, z = project(inner_cam(th))
            tr.append(f"{f(X)},{f(Y)}")
            rs.append(f(s, 3))
            far_flags.append(z > 0)
        # exact crossing times by bisection of z(theta)
        def zt(u):
            return inner_cam(ph - 360.0 * u)[2]
        cross = []
        for k in range(ORB_N):
            u0, u1 = k / ORB_N, (k + 1) / ORB_N
            if (zt(u0) > 0) != (zt(u1) > 0):
                lo, hi = u0, u1
                for _ in range(40):
                    mid = (lo + hi) / 2
                    if (zt(mid) > 0) == (zt(lo) > 0):
                        lo = mid
                    else:
                        hi = mid
                cross.append(((lo + hi) / 2, zt(u1) > 0))
        assert len(cross) == 2
        # far interval: from the crossing that enters far to the one that leaves
        enter = next(u for u, into_far in cross if into_far)
        leave = next(u for u, into_far in cross if not into_far)
        for far in (True, False):
            iv = [(enter, leave)] if far else [(leave, enter)]
            first, vis_anim = discrete_vis(iv, ORB_T)
            orb_layers[far].append(
                f'<g visibility="{first}">{vis_anim}'
                f'<g transform="translate({tr[0]})">'
                f'<animateTransform attributeName="transform" type="translate" dur="{f(ORB_T)}s" repeatCount="indefinite" values="{";".join(tr)}"/>'
                f'<g transform="scale({rs[0]})">'
                f'<animateTransform attributeName="transform" type="scale" dur="{f(ORB_T)}s" repeatCount="indefinite" values="{";".join(rs)}"/>'
                f'<circle r="{f(rad * 3.2)}" fill="{col}" opacity="{".1" if far else ".16"}"/>'
                f'<circle r="{f(rad * 1.7)}" fill="{col}" opacity="{".18" if far else ".3"}"/>'
                f'<circle r="{f(rad)}" fill="{col}" opacity="{".5" if far else "1"}"/>'
                f'</g></g></g>')
    for s in orb_layers[True]:
        doc.b(s)

    # ------------------------------------------------ the core: holographic wireframe globe
    def gpoint(lat_deg, lon_deg, rscale=1.0):
        la, lo = math.radians(lat_deg), math.radians(lon_deg)
        p = (rscale * math.cos(la) * math.cos(lo), rscale * math.sin(la), rscale * math.cos(la) * math.sin(lo))
        p = rot_x(p, G_PITCH)
        p = rot_z(p, G_ROLL)
        x, y, z = cam(p)
        return CX + GR * x, CY - GR * y, z

    def depth_op(z, lo=0.13, hi=0.95):
        return lerp(hi, lo, smooth(-0.3, 0.3, z))

    doc.b(f'<circle cx="{f(CX)}" cy="{f(CY)}" r="{f(GR + 26)}" fill="url(#limeGlow)"/>')
    doc.b(f'<circle cx="{f(CX)}" cy="{f(CY)}" r="{f(GR + 18)}" fill="url(#atmo)"/>')
    doc.b(f'<circle cx="{f(CX)}" cy="{f(CY)}" r="{f(GR)}" fill="url(#globeFill)" fill-opacity="0.96"/>')

    # polar axis (static), drawn first so lines sit on top
    npx, npy, _ = gpoint(90, 0, 1.32)
    spx, spy, _ = gpoint(-90, 0, 1.32)
    doc.b(f'<path d="M{f(npx)} {f(npy)}L{f(spx)} {f(spy)}" stroke="{LIME}" stroke-opacity="0.35" '
          f'stroke-width="1" stroke-dasharray="2 4"/>')

    # latitudes: static, cut into short pieces with depth opacity
    for lat in LATS:
        col = LIME if lat == 0 else "url(#holoG)"
        sw = 1.5 if lat == 0 else 1.1
        step = 15.0
        pieces = []
        for k in range(int(360 / step)):
            l0, l1 = k * step, (k + 1) * step
            pts = [gpoint(lat, l0 + (l1 - l0) * j / 3) for j in range(4)]
            zm = gpoint(lat, (l0 + l1) / 2)[2]
            pieces.append((f(depth_op(zm, 0.1, 0.95 if lat else 1.0), 2),
                           "M" + "L".join(f"{f(x)} {f(y)}" for x, y, _ in pts)))
        # merge consecutive pieces with equal opacity
        merged = []
        for op, d in pieces:
            if merged and merged[-1][0] == op:
                merged[-1][1].append(d.replace("M", "L", 1))
            else:
                merged.append((op, [d]))
        doc.b(f'<g fill="none" stroke="{col}" stroke-width="{sw}" stroke-linecap="round">'
              + "".join(f'<path d="{"".join(ds)}" opacity="{op}"/>' for op, ds in merged) + '</g>')

    # meridians: animated over one 30 deg symmetry period
    per_dur = G_SPIN_T * MER_STEP / 360.0
    bands = [(-90, -60), (-60, -30), (-30, 0), (0, 30), (30, 60), (60, 90)]
    doc.b(f'<g fill="none" stroke="url(#holoG)" stroke-width="1.1" stroke-linecap="round">')
    for m in range(MERID):
        lon0 = m * MER_STEP
        for (la0, la1) in bands:
            ds, ops = [], []
            for k in range(MER_FRAMES + 1):
                lon = lon0 - MER_STEP * k / MER_FRAMES
                h = (la1 - la0) / 2.0
                mid = (la0 + la1) / 2.0
                x0, y0, _ = gpoint(la0, lon)
                x1, y1, _ = gpoint(la1, lon)
                cx_, cy_, _ = gpoint(mid, lon, 1.0 / math.cos(math.radians(h)))
                zm = gpoint(mid, lon)[2]
                ds.append(f"M{f(x0)} {f(y0)}Q{f(cx_)} {f(cy_)} {f(x1)} {f(y1)}")
                ops.append(f(depth_op(zm), 2))
            doc.b(f'<path d="{ds[0]}" opacity="{ops[0]}">'
                  f'<animate attributeName="d" dur="{f(per_dur, 3)}s" repeatCount="indefinite" values="{";".join(ds)}"/>'
                  f'<animate attributeName="opacity" dur="{f(per_dur, 3)}s" repeatCount="indefinite" values="{";".join(ops)}"/>'
                  f'</path>')
    doc.b('</g>')

    # glowing nodes on the surface, full spin
    nodes = [(28, 20), (-22, 110), (48, 200), (-40, 260), (8, 315)]
    gn = 48
    for la, lo in nodes:
        tr, ops = [], []
        for k in range(gn + 1):
            x, y, z = gpoint(la, lo - 360.0 * k / gn)
            tr.append(f"{f(x)},{f(y)}")
            ops.append(f(lerp(1.0, 0.0, smooth(-0.15, 0.12, z)), 2))
        doc.b(f'<g transform="translate({tr[0]})" opacity="{ops[0]}">'
              f'<animateTransform attributeName="transform" type="translate" dur="{f(G_SPIN_T)}s" repeatCount="indefinite" values="{";".join(tr)}"/>'
              f'<animate attributeName="opacity" dur="{f(G_SPIN_T)}s" repeatCount="indefinite" values="{";".join(ops)}"/>'
              f'<circle r="6" fill="{LIME}" opacity="0.18"/><circle r="2.4" fill="{LIME}"/></g>')

    # rim + specular
    doc.b(f'<circle cx="{f(CX)}" cy="{f(CY)}" r="{f(GR)}" fill="none" stroke="url(#rimG)" stroke-opacity="0.9" stroke-width="1.6"/>')
    doc.b(f'<ellipse cx="{f(CX - GR * .38)}" cy="{f(CY - GR * .45)}" rx="{f(GR * .36)}" ry="{f(GR * .2)}" '
          f'transform="rotate(-32 {f(CX - GR * .38)} {f(CY - GR * .45)})" fill="url(#spec)"/>')

    # ------------------------------------------------ inner ring near half + near orbs
    doc.b(f'<g opacity="0.55">{ripple(False)}</g>')
    doc.b(dashed(near_run, plen(far_run), 0.6, 1.3))
    for s in orb_layers[False]:
        doc.b(s)

    # ------------------------------------------------ front layer tags
    doc.b('<g id="front">')
    for i in range(n_tags):
        doc.b(tag_instance(i, True))
    doc.b('</g>')

    doc.b('</g>')  # clip
    doc.b(f'<rect x="0.5" y="0.5" width="{VW - 1}" height="{VH - 1}" rx="21.5" fill="none" stroke="{HAIR}"/>')

    names = ", ".join(n for n, _, _ in TAGS)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{VW}" height="{VH}" '
           f'viewBox="0 0 {VW} {VH}" role="img" aria-label="stack: {names}">\n'
           f'<title>stack</title>\n<defs>\n' + "\n".join(doc.defs) + '\n</defs>\n'
           + "\n".join(doc.body) + '\n</svg>\n')
    return svg


def main():
    svg = build()
    ET.fromstring(svg)  # validate XML
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {OUT} ({len(svg.encode('utf-8')) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
