#!/usr/bin/env python3
"""Generate assets/hero.svg -- the animated hero banner for the zqh7y profile README.

Deterministic, stdlib only. Run:  python3 src/hero.py

Everything is inline (no scripts, fonts, images or links) so GitHub's camo
proxy serves it as a plain <img>. Motion uses CSS @keyframes and SMIL only,
and every loop is seamless:

* the 3D centerpiece is a holographic icosahedron with a lime octahedron core.
  Rotation is precomputed here (rotation matrices + perspective projection)
  and played back through SMIL `values` lists. The angles complete whole turns
  inside one duration, so the last frame equals the first.
* the synthwave floor scrolls exactly one grid spacing per loop.
* the typing line is a discrete SMIL timeline that ends where it starts.
"""
import math
import os
import random

W, H = 1000, 340
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "assets", "hero.svg"))

# palette (matches the portfolio)
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


# --------------------------------------------------------------------------
# number formatting (keeps the file small)
# --------------------------------------------------------------------------
def n1(v):
    s = f"{v:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return "0" if s in ("-0", "") else s


def n2(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return "0" if s in ("", "-0", "-") else s


def n4(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


# --------------------------------------------------------------------------
# 3D helpers
# --------------------------------------------------------------------------
def rx(a):
    c, s = math.cos(a), math.sin(a)
    return ((1, 0, 0), (0, c, -s), (0, s, c))


def ry(a):
    c, s = math.cos(a), math.sin(a)
    return ((c, 0, s), (0, 1, 0), (-s, 0, c))


def rz(a):
    c, s = math.cos(a), math.sin(a)
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def mm(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def mv(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def norm(v):
    l = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / l for c in v)


def sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def icosahedron():
    p = (1 + 5 ** 0.5) / 2
    raw = []
    for a in (-1, 1):
        for b in (-1, 1):
            raw += [(0, a, b * p), (a, b * p, 0), (b * p, 0, a)]
    edges = [(i, j) for i in range(12) for j in range(i + 1, 12)
             if abs(sum((raw[i][k] - raw[j][k]) ** 2 for k in range(3)) - 4) < 1e-6]
    es = set(edges)
    faces = [(i, j, k) for i in range(12) for j in range(i + 1, 12) for k in range(j + 1, 12)
             if (i, j) in es and (j, k) in es and (i, k) in es]
    verts = [norm(v) for v in raw]
    # orient faces outward
    out = []
    for f in faces:
        a, b, c = (verts[i] for i in f)
        n = cross(sub(b, a), sub(c, a))
        cen = tuple((a[i] + b[i] + c[i]) / 3 for i in range(3))
        out.append(f if dot(n, cen) > 0 else (f[0], f[2], f[1]))
    return verts, edges, out


def octahedron():
    verts = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
    edges = [(i, j) for i in range(6) for j in range(i + 1, 6) if dot(verts[i], verts[j]) > -0.5]
    return verts, edges


def hamiltonian_cycle(nv, edges):
    adj = {i: sorted(j for e in edges for j in e if i in e and j != i) for i in range(nv)}
    path = [0]

    def dfs():
        if len(path) == nv:
            return path[0] in adj[path[-1]]
        for nb in adj[path[-1]]:
            if nb not in path:
                path.append(nb)
                if dfs():
                    return True
                path.pop()
        return False

    assert dfs()
    return path


# --------------------------------------------------------------------------
# scene constants
# --------------------------------------------------------------------------
OCX, OCY = 776, 148        # object center (screen)
ORAD = 112                 # object radius (px at depth 0)
CAM = 4.6                  # camera distance (unit radius object)
NF = 60                    # rotation frames per loop
T_ROT = 20.0               # seconds per full loop
HY = 246                   # horizon y
VPX = OCX                  # vanishing point x


def project(p, scale=ORAD):
    s = CAM / (CAM - p[2])
    return (OCX + p[0] * scale * s, OCY - p[1] * scale * s)


def outer_rot(k):
    th = 2 * math.pi * k / NF
    return mm(rz(0.30), mm(rx(-0.32), mm(ry(2 * th), rx(th))))


def inner_rot(k):
    th = 2 * math.pi * k / NF
    return mm(rz(-0.2), mm(ry(-3 * th), rz(th)))


LIGHT = norm((-0.55, 0.75, 0.65))


def vals(seq):
    return ";".join(seq)


def anim(attr, values, dur=T_ROT, extra=""):
    return (f'<animate attributeName="{attr}" dur="{dur}s" repeatCount="indefinite" '
            f'values="{vals(values)}"{extra}/>')


def build_object():
    verts, edges, faces = icosahedron()
    over, oedges = octahedron()
    frames_o = [[mv(outer_rot(k), v) for v in verts] for k in range(NF + 1)]
    frames_i = [[tuple(c * 0.40 for c in mv(inner_rot(k), v)) for v in over] for k in range(NF + 1)]
    frames_o[NF] = frames_o[0]
    frames_i[NF] = frames_i[0]

    out = []

    # ---- faces: faint iridescent glass, only front-facing ones lit
    face_parts = []
    for f in faces:
        ds, ops = [], []
        for k in range(NF + 1):
            P = [frames_o[k][i] for i in f]
            sp = [project(p) for p in P]
            ds.append("M" + "L".join(f"{n1(x)} {n1(y)}" for x, y in sp) + "Z")
            n = norm(cross(sub(P[1], P[0]), sub(P[2], P[0])))
            cen = tuple(sum(p[i] for p in P) / 3 for i in range(3))
            view = norm(sub((0, 0, CAM), cen))
            facing = dot(n, view)
            lit = max(0.0, dot(n, LIGHT))
            spec = max(0.0, dot(norm(tuple(LIGHT[i] + view[i] for i in range(3))), n)) ** 40
            if facing <= 0:
                op = 0.0
            else:
                op = 0.03 + 0.10 * lit + 0.20 * spec
            ops.append(n2(op))
        face_parts.append(
            f'<path d="{ds[0]}" fill-opacity="{ops[0]}">'
            + anim("d", ds) + anim("fill-opacity", ops) + "</path>")
    out.append('<g class="faces" fill="url(#holo)">' + "".join(face_parts) + "</g>")

    # ---- edges (outer icosahedron), depth shaded + holo colored
    # each edge animates only its shape and opacity: per-element width and
    # colour animations were the main paint cost, so depth reads through
    # opacity alone and colour comes from a shared gradient on the group
    def edge_markup(frames, eds, omin, omax, scale_tag):
        parts = []
        for (a, b) in eds:
            x1s, y1s, x2s, y2s, os_ = [], [], [], [], []
            for k in range(NF + 1):
                pa, pb = frames[k][a], frames[k][b]
                (sx1, sy1), (sx2, sy2) = project(pa), project(pb)
                x1s.append(n1(sx1)); y1s.append(n1(sy1)); x2s.append(n1(sx2)); y2s.append(n1(sy2))
                zm = (pa[2] + pb[2]) / 2 / scale_tag
                t = max(0.0, min(1.0, (zm + 1) / 2))
                os_.append(n2(omin + (omax - omin) * t ** 1.6))
            ds = [f"M{x1s[k]} {y1s[k]}L{x2s[k]} {y2s[k]}" for k in range(NF + 1)]
            parts.append(f'<path d="{ds[0]}" stroke-opacity="{os_[0]}">'
                         + anim("d", ds) + anim("stroke-opacity", os_) + "</path>")
        return "".join(parts)

    wire_outer = edge_markup(frames_o, edges, 0.1, 1.0, 1.0)
    wire_inner = edge_markup(frames_i, oedges, 0.25, 1.0, 0.40)
    out.append(f'<g id="wire" fill="none" stroke="url(#holo)" stroke-width="1.7" '
               f'stroke-linecap="round">{wire_outer}</g>')

    # ---- vertices
    vparts = []
    for i in range(len(verts)):
        cx, cy, ops = [], [], []
        for k in range(NF + 1):
            p = frames_o[k][i]
            x, y = project(p)
            t = (p[2] + 1) / 2
            cx.append(n1(x)); cy.append(n1(y))
            ops.append(n2(0.18 + 0.82 * t ** 1.6))
        vparts.append(f'<circle cx="{cx[0]}" cy="{cy[0]}" r="2.2" opacity="{ops[0]}">'
                      + anim("cx", cx) + anim("cy", cy) + anim("opacity", ops)
                      + "</circle>")
    out.append(f'<g id="verts" fill="{TEXT}">' + "".join(vparts) + "</g>")

    # ---- lime core
    out.append(f'<g id="core" fill="none" stroke="{LIME}" stroke-width="1.3" '
               f'stroke-linecap="round">{wire_inner}</g>')

    # ---- lime pulses running along a hamiltonian cycle of the shell
    cyc = hamiltonian_cycle(12, edges)
    per = NF // len(cyc)
    assert per * len(cyc) == NF

    def pulse_track(cycle):
        cx, cy, rs, ops = [], [], [], []
        for k in range(NF + 1):
            kk = k % NF
            e, fr = divmod(kk, per)
            a, b = cycle[e], cycle[(e + 1) % len(cycle)]
            u = fr / per
            va, vb = verts[a], verts[b]
            p0 = tuple(va[i] + (vb[i] - va[i]) * u for i in range(3))
            p = mv(outer_rot(kk), p0)
            x, y = project(p)
            t = (p[2] + 1) / 2
            cx.append(n1(x)); cy.append(n1(y))
            rs.append(n2(1.6 + 2.4 * t))
            ops.append(n2(0.25 + 0.75 * t ** 1.4))
        return cx, cy, rs, ops

    pparts = []
    tracks = [pulse_track(cyc), pulse_track(list(reversed(cyc[6:] + cyc[:6])))]
    for ti, (cx, cy, rs, ops) in enumerate(tracks):
        for j, lag in enumerate((0.0, 0.1)):
            scale = (1.0, 0.65)[j]
            fade = (1.0, 0.4)[j]
            begin = f' begin="{n2(lag - T_ROT)}s"' if lag else ""
            rs_j = [n2(float("0" + r if r.startswith(".") else r) * scale) for r in rs]
            ops_j = [n2(float("0" + o if o.startswith(".") else o) * fade) for o in ops]
            pparts.append(f'<circle cx="{cx[0]}" cy="{cy[0]}" r="{rs_j[0]}" opacity="0">'
                          + anim("cx", cx, extra=begin) + anim("cy", cy, extra=begin)
                          + anim("r", rs_j, extra=begin) + anim("opacity", ops_j, extra=begin)
                          + "</circle>")
    out.append(f'<g id="pulses" fill="{LIME}">' + "".join(pparts) + "</g>")
    return out


# --------------------------------------------------------------------------
# orbit ring + satellite (back half drawn behind the solid, front half after)
# --------------------------------------------------------------------------
RING_R = 1.58
RING_ROT = mm(rz(-0.24), rx(0.30))
SAT_DUR = 10.0


def ring_point(phi):
    return mv(RING_ROT, (RING_R * math.cos(phi), 0.0, RING_R * math.sin(phi)))


def build_ring():
    n = 160
    pts = [ring_point(2 * math.pi * i / n) for i in range(n + 1)]
    back, front = [], []
    cur, cur_side = [], None
    runs = []
    for p in pts:
        side = p[2] >= 0
        if cur_side is None or side == cur_side:
            cur.append(p)
        else:
            cur.append(p)
            runs.append((cur_side, cur))
            cur = [p]
        cur_side = side
    runs.append((cur_side, cur))
    for side, run in runs:
        d = "M" + "L".join(f"{n1(x)} {n1(y)}" for x, y in (project(p) for p in run))
        (front if side else back).append(d)
    # satellite: one copy behind, one in front; opacity flips with depth sign
    cx, cy, rs, ob, of = [], [], [], [], []
    for k in range(NF + 1):
        p = ring_point(-2 * math.pi * k / NF + 0.6)
        x, y = project(p)
        t = (p[2] / RING_R + 1) / 2
        cx.append(n1(x)); cy.append(n1(y))
        rs.append(n2(2.4 + 2.2 * t))
        of.append("1" if p[2] >= 0 else "0")
        ob.append("0" if p[2] >= 0 else n2(0.35 + 0.4 * t))

    def sat(opv, idv):
        return (f'<circle id="{idv}" cx="{cx[0]}" cy="{cy[0]}" r="{rs[0]}" opacity="{opv[0]}">'
                + anim("cx", cx, SAT_DUR) + anim("cy", cy, SAT_DUR) + anim("r", rs, SAT_DUR)
                + anim("opacity", opv, SAT_DUR) + "</circle>")

    back_svg = (f'<path d="{"".join(back)}" fill="none" stroke="url(#ringG)" stroke-width="1" '
                f'stroke-opacity=".28"/>' + f'<g fill="{LIME}">{sat(ob, "satB")}</g>')
    front_svg = (f'<path d="{"".join(front)}" fill="none" stroke="url(#ringG)" stroke-width="1.4" '
                 f'stroke-opacity=".7"/>'
                 f'<g fill="{LIME}">{sat(of, "satF")}</g>')
    return back_svg, front_svg


# --------------------------------------------------------------------------
# floor grid
# --------------------------------------------------------------------------
FLOOR_K = 98.0        # y offset of depth z=1 below horizon
FLOOR_FRAMES = 24
FLOOR_DUR = 1.6
FLOOR_SPACING = 1.0


def build_floor():
    rows = []
    zs0 = [1.0 + i * FLOOR_SPACING for i in range(16)]
    for f in range(FLOOR_FRAMES + 1):
        ph = FLOOR_SPACING * f / FLOOR_FRAMES
        d = []
        for z0 in zs0:
            z = z0 - ph
            y = HY + FLOOR_K / max(z, 0.05)
            y = min(y, H + 40)
            d.append(f"M0 {n1(y)}H{W}")
        rows.append("".join(d))
    horiz = (f'<path d="{rows[0]}" fill="none">'
             f'<animate attributeName="d" dur="{FLOOR_DUR}s" repeatCount="indefinite" '
             f'values="{vals(rows)}"/></path>')
    rad = []
    G = 0.62  # world spacing of the depth lines
    for j in range(-26, 9):
        xb = VPX + j * G * FLOOR_K * 1.0 / 0.30   # at z = 0.30 (well below the frame)
        yb = HY + FLOOR_K / 0.30
        rad.append(f"M{n1(VPX)} {HY}L{n1(xb)} {n1(yb)}")
    radial = f'<path d="{"".join(rad)}" fill="none"/>'
    return horiz, radial


# --------------------------------------------------------------------------
# typing line
# --------------------------------------------------------------------------
TY_X, TY_Y, TY_SIZE = 52, 280, 26   # '›' is centred in its cell: x=52 puts its ink on the text column
CW = TY_SIZE * 0.6
WORDS = ["apps.", "web.", "games.", "programs."]
PREFIX = "› i build "
T_TYPE, T_HOLD, T_ERASE, T_GAP = 0.085, 1.75, 0.04, 0.38


def build_typing():
    t = T_GAP / 2          # half the gap here, half after the last word -> even seam
    spans = []          # (word, [(appear, vanish) per char])
    cursor = []         # (time, col, solid)
    cursor.append((0.0, 0, False))
    for w in WORDS:
        n = len(w)
        s = t
        appear = [s + j * T_TYPE for j in range(n)]
        typed = s + n * T_TYPE
        e = typed + T_HOLD
        vanish = [e + (n - 1 - j) * T_ERASE for j in range(n)]
        spans.append((w, list(zip(appear, vanish))))
        for j in range(n):
            cursor.append((appear[j], j + 1, True))
        cursor.append((typed, n, False))
        for j in range(n):
            cursor.append((vanish[j], j, True))
        cursor.append((e + n * T_ERASE, 0, False))
        t = e + n * T_ERASE + T_GAP
    total = t - T_GAP / 2
    # first word fully typed, slightly into hold -> t=0 of the svg
    offset = T_GAP / 2 + len(WORDS[0]) * T_TYPE + 0.25

    # cursor discrete timeline: solid while typing, blinking otherwise
    keys = []
    cursor.sort(key=lambda c: c[0])
    for idx, (tc, col, solid) in enumerate(cursor):
        tn = cursor[idx + 1][0] if idx + 1 < len(cursor) else total
        if solid:
            keys.append((tc, col, 1))
        else:
            tt, on = tc, True
            while tt < tn - 1e-9:
                keys.append((tt, col, 1 if on else 0))
                tt += 0.5
                on = not on
    # dedupe/merge equal times
    merged = []
    for k in keys:
        if merged and abs(merged[-1][0] - k[0]) < 1e-6:
            merged[-1] = k
        else:
            merged.append(k)
    kt = ";".join(n4(k[0] / total) for k in merged)
    base = len(PREFIX)
    xs = ";".join(n1(TY_X + (base + k[1]) * CW) for k in merged)
    ops = ";".join(str(k[2]) for k in merged)
    begin = f'begin="-{n4(offset)}s"'
    common = f'dur="{n4(total)}s" repeatCount="indefinite" calcMode="discrete" {begin}'

    parts = []
    px = " ".join(n1(TY_X + i * CW) for i in range(len(PREFIX)))
    parts.append(f'<text x="{px}" y="{TY_Y}" font-family="{MONO}" font-size="{TY_SIZE}" '
                 f'fill="{TEXT}"><tspan fill="{MUTED}">›</tspan> i build </text>')
    chars = []
    for wi, (w, ts) in enumerate(spans):
        # base value only matters where SMIL does not run: show the first word
        op0 = "1" if wi == 0 else "0"
        for j, (a, v) in enumerate(ts):
            x = TY_X + (base + j) * CW
            chars.append(
                f'<text x="{n1(x)}" y="{TY_Y}" opacity="{op0}">{w[j]}'
                f'<animate attributeName="opacity" values="0;1;0" '
                f'keyTimes="0;{n4(a / total)};{n4(v / total)}" {common}/></text>')
    parts.append(f'<g font-family="{MONO}" font-size="{TY_SIZE}" fill="{LIME}" font-weight="600">'
                 + "".join(chars) + "</g>")
    cx0 = TY_X + (base + len(WORDS[0])) * CW
    parts.append(
        f'<rect class="cursor" x="{n1(cx0)}" y="{TY_Y - 21}" width="{n1(CW * 0.62)}" height="26" '
        f'rx="1.5" fill="{LIME}">'
        f'<animate attributeName="x" values="{xs}" keyTimes="{kt}" {common}/>'
        f'<animate attributeName="opacity" values="{ops}" keyTimes="{kt}" {common}/>'
        f'</rect>')
    return "".join(parts)


# --------------------------------------------------------------------------
# stars
# --------------------------------------------------------------------------
def build_stars():
    rnd = random.Random(20240607)
    parts = []
    n = 0
    tries = 0
    pts = []
    while n < 40 and tries < 4000:
        tries += 1
        x, y = rnd.uniform(18, W - 18), rnd.uniform(14, HY - 14)
        if any((x - a) ** 2 + (y - b) ** 2 < 34 ** 2 for a, b in pts):
            continue
        if x < 490 and y > 30:      # keep the text column clean
            continue
        pts.append((x, y))
        n += 1
        r = rnd.choice((0.7, 0.8, 0.9, 1.0, 1.1, 1.3, 1.6))
        col = rnd.choice((TEXT, TEXT, TEXT, TEXT, CYAN, VIOLET, LIME))
        dur = rnd.choice((2.6, 3.4, 4.2, 5.0, 6.2))
        delay = -rnd.uniform(0, dur)
        parts.append(f'<circle cx="{n1(x)}" cy="{n1(y)}" r="{r}" fill="{col}" '
                     f'style="animation-duration:{dur}s;animation-delay:{n2(delay)}s"/>')
    # a few sparkle crosses
    spark = []
    for (x, y, s, d) in ((612, 40, 5, 0.0), (946, 58, 4, -2.1), (520, 116, 3.5, -3.7), (930, 214, 3.5, -1.2)):
        spark.append(f'<path class="spark" d="M{x - s} {y}H{x + s}M{x} {y - s}V{y + s}" '
                     f'style="animation-delay:{d}s"/>')
    return "".join(parts), "".join(spark)


# --------------------------------------------------------------------------
# assemble
# --------------------------------------------------------------------------
def build():
    stars, sparks = build_stars()
    horiz, radial = build_floor()
    obj = build_object()
    ring_back, ring_front = build_ring()
    typing = build_typing()

    NAME_X, NAME_Y, NAME_SIZE, NAME_LEN = 52, 178, 108, 372
    name_attrs = (f'x="{NAME_X}" y="{NAME_Y}" font-family="{SANS}" font-size="{NAME_SIZE}" '
                  f'font-weight="800" letter-spacing="-2" textLength="{NAME_LEN}" '
                  f'lengthAdjust="spacingAndGlyphs"')

    css = f"""
.stars circle{{animation-name:tw;animation-timing-function:ease-in-out;animation-iteration-count:infinite}}
@keyframes tw{{0%,100%{{opacity:.12}}50%{{opacity:.85}}}}
.spark{{stroke:{TEXT};stroke-width:1.2;stroke-linecap:round;opacity:0;animation:sp 6s ease-in-out infinite}}
@keyframes sp{{0%,100%{{opacity:0}}12%{{opacity:.9}}24%{{opacity:0}}}}
.glA{{animation:glA 9s steps(1,end) infinite}}
.glB{{animation:glB 9s steps(1,end) infinite}}
@keyframes glA{{0%{{opacity:0;transform:translate(0,0)}}86%{{opacity:.9;transform:translate(-6px,0)}}87%{{transform:translate(4px,0)}}88%{{transform:translate(-3px,0)}}89%{{opacity:0;transform:translate(0,0)}}93%{{opacity:.8;transform:translate(5px,0)}}93.6%{{opacity:0}}100%{{opacity:0}}}}
@keyframes glB{{0%{{opacity:0;transform:translate(0,0)}}86.4%{{opacity:.9;transform:translate(6px,0)}}87.4%{{transform:translate(-5px,0)}}88.4%{{opacity:0;transform:translate(0,0)}}93.2%{{opacity:.8;transform:translate(-4px,0)}}93.8%{{opacity:0}}100%{{opacity:0}}}}
.nm{{animation:nm 9s steps(1,end) infinite}}
@keyframes nm{{0%{{transform:translate(0,0)}}86.5%{{transform:translate(2px,0)}}87.5%{{transform:translate(-1px,0)}}88.5%{{transform:translate(0,0)}}100%{{transform:translate(0,0)}}}}
.bob{{animation:bob 6s ease-in-out infinite}}
@keyframes bob{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-7px)}}}}
.shadow{{transform-box:fill-box;transform-origin:center;animation:sh 6s ease-in-out infinite}}
@keyframes sh{{0%,100%{{transform:scale(1);opacity:.9}}50%{{transform:scale(.86);opacity:.6}}}}
.halo{{transform-box:fill-box;transform-origin:center;animation:halo 6s ease-in-out infinite}}
@keyframes halo{{0%,100%{{opacity:.85;transform:scale(1)}}50%{{opacity:1;transform:scale(1.06)}}}}
.ping{{transform-box:fill-box;transform-origin:center;animation:ping 2s ease-out infinite}}
@keyframes ping{{0%{{transform:scale(1);opacity:.7}}80%,100%{{transform:scale(2.8);opacity:0}}}}
"""

    s = []
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
             f'width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
             f'aria-labelledby="t d">')
    s.append('<title id="t">zzqxck</title>')
    s.append('<desc id="d">zzqxck: full-stack dev from holon, il. i build apps, web, games and programs. '
             'currently building metz.</desc>')
    s.append(f"<style>{css}</style>")
    s.append("<defs>")
    s.append(f'<clipPath id="frame"><rect width="{W}" height="{H}" rx="22"/></clipPath>')
    s.append(f'<radialGradient id="bgL" cx="150" cy="120" r="420" gradientUnits="userSpaceOnUse">'
             f'<stop offset="0" stop-color="{LIME}" stop-opacity=".07"/>'
             f'<stop offset="1" stop-color="{LIME}" stop-opacity="0"/></radialGradient>')
    s.append(f'<radialGradient id="glow" cx="{OCX}" cy="{OCY}" r="190" gradientUnits="userSpaceOnUse">'
             f'<stop offset="0" stop-color="{VIOLET}" stop-opacity=".34"/>'
             f'<stop offset=".35" stop-color="{CYAN}" stop-opacity=".12"/>'
             f'<stop offset=".7" stop-color="{PINK}" stop-opacity=".04"/>'
             f'<stop offset="1" stop-color="{PINK}" stop-opacity="0"/></radialGradient>')
    s.append(f'<linearGradient id="holo" x1="{OCX - 90}" y1="{OCY - 80}" x2="{OCX + 90}" y2="{OCY + 80}" '
             f'gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{CYAN}"/>'
             f'<stop offset=".5" stop-color="{VIOLET}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>')
    s.append(f'<linearGradient id="ringG" x1="{OCX - 185}" y1="0" x2="{OCX + 185}" y2="0" '
             f'gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{CYAN}" stop-opacity=".1"/>'
             f'<stop offset=".25" stop-color="{CYAN}"/><stop offset=".55" stop-color="{VIOLET}"/>'
             f'<stop offset=".8" stop-color="{PINK}"/>'
             f'<stop offset="1" stop-color="{PINK}" stop-opacity=".1"/></linearGradient>')
    s.append(f'<radialGradient id="shadowG"><stop offset="0" stop-color="{LIME}" stop-opacity=".45"/>'
             f'<stop offset=".5" stop-color="{VIOLET}" stop-opacity=".14"/>'
             f'<stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>')
    s.append(f'<radialGradient id="vig" cx="500" cy="170" r="640" gradientUnits="userSpaceOnUse">'
             f'<stop offset=".55" stop-color="#000" stop-opacity="0"/>'
             f'<stop offset="1" stop-color="#000" stop-opacity=".6"/></radialGradient>')
    # floor fade: ink overlays at the horizon and toward the text column
    # (static gradients instead of a mask, which would be recomposited every frame)
    s.append(f'<linearGradient id="fadeV" x1="0" y1="{HY}" x2="0" y2="{H}" gradientUnits="userSpaceOnUse">'
             f'<stop offset="0" stop-color="{INK}"/><stop offset=".075" stop-color="{INK}"/>'
             f'<stop offset=".2" stop-color="{INK}" stop-opacity=".67"/>'
             f'<stop offset=".5" stop-color="{INK}" stop-opacity=".31"/>'
             f'<stop offset="1" stop-color="{INK}" stop-opacity="0"/></linearGradient>')
    s.append(f'<linearGradient id="fadeH" x1="0" y1="0" x2="{W}" y2="0" gradientUnits="userSpaceOnUse">'
             f'<stop offset="0" stop-color="{INK}" stop-opacity=".82"/>'
             f'<stop offset=".5" stop-color="{INK}" stop-opacity=".25"/>'
             f'<stop offset=".7" stop-color="{INK}" stop-opacity="0"/>'
             f'<stop offset="1" stop-color="{INK}" stop-opacity=".2"/></linearGradient>')
    s.append(f'<linearGradient id="horizon" x1="0" y1="0" x2="{W}" y2="0" gradientUnits="userSpaceOnUse">'
             f'<stop offset="0" stop-color="{LIME}" stop-opacity="0"/>'
             f'<stop offset=".45" stop-color="{LIME}" stop-opacity=".25"/>'
             f'<stop offset=".77" stop-color="{LIME}" stop-opacity=".9"/>'
             f'<stop offset="1" stop-color="{LIME}" stop-opacity=".15"/></linearGradient>')
    s.append(f'<linearGradient id="floorFill" x1="0" y1="{HY}" x2="0" y2="{H}" gradientUnits="userSpaceOnUse">'
             f'<stop offset="0" stop-color="{LIME}" stop-opacity=".07"/>'
             f'<stop offset=".35" stop-color="{VIOLET}" stop-opacity=".03"/>'
             f'<stop offset="1" stop-color="{INK}" stop-opacity="0"/></linearGradient>')
    # name sheen: diagonal holo band sweeping across, repeating gradient => seamless
    s.append(f'<linearGradient id="sheen" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="1100" y2="0" '
             f'spreadMethod="repeat" gradientTransform="skewX(-24)">'
             f'<stop offset="0" stop-color="{LIME}" stop-opacity="0"/>'
             f'<stop offset=".30" stop-color="{LIME}" stop-opacity="0"/>'
             f'<stop offset=".345" stop-color="{LIME}" stop-opacity=".95"/>'
             f'<stop offset=".38" stop-color="{CYAN}" stop-opacity=".95"/>'
             f'<stop offset=".415" stop-color="{VIOLET}" stop-opacity=".95"/>'
             f'<stop offset=".45" stop-color="{PINK}" stop-opacity=".9"/>'
             f'<stop offset=".5" stop-color="{PINK}" stop-opacity="0"/>'
             f'<stop offset="1" stop-color="{PINK}" stop-opacity="0"/>'
             f'<animateTransform attributeName="gradientTransform" type="translate" additive="sum" '
             f'from="-200 0" to="900 0" dur="7s" repeatCount="indefinite"/></linearGradient>')
    s.append(f'<linearGradient id="nameBase" x1="0" y1="96" x2="0" y2="186" gradientUnits="userSpaceOnUse">'
             f'<stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#cfcfc8"/></linearGradient>')
    s.append('<clipPath id="sliceA"><rect x="0" y="104" width="560" height="16"/>'
             '<rect x="0" y="150" width="560" height="9"/></clipPath>')
    s.append('<clipPath id="sliceB"><rect x="0" y="126" width="560" height="12"/>'
             '<rect x="0" y="164" width="560" height="22"/></clipPath>')
    s.append("</defs>")

    s.append('<g clip-path="url(#frame)">')
    s.append(f'<rect width="{W}" height="{H}" fill="{INK}"/>')
    s.append(f'<rect width="{W}" height="{H}" fill="url(#bgL)"/>')
    s.append(f'<g class="stars">{stars}</g>{sparks}')

    # floor
    s.append(f'<g stroke="{LIME}" stroke-width="1.1" stroke-opacity=".55">{radial}{horiz}</g>')
    s.append(f'<rect y="{HY}" width="{W}" height="{H - HY}" fill="url(#fadeV)"/>')
    s.append(f'<rect y="{HY}" width="{W}" height="{H - HY}" fill="url(#fadeH)"/>')
    s.append(f'<rect y="{HY}" width="{W}" height="{H - HY}" fill="url(#floorFill)"/>')
    s.append(f'<rect x="0" y="{HY - 0.6}" width="{W}" height="1.2" fill="url(#horizon)"/>')
    s.append(f'<rect x="0" y="{HY - 3}" width="{W}" height="6" fill="url(#horizon)" opacity=".18"/>')

    # 3D centerpiece
    s.append(f'<circle class="halo" cx="{OCX}" cy="{OCY}" r="190" fill="url(#glow)"/>')
    s.append(f'<ellipse class="shadow" cx="{OCX}" cy="{HY + 46}" rx="132" ry="15" fill="url(#shadowG)"/>')
    s.append('<g class="bob">')
    faces, wire, verts, core, pulses = obj
    s.append(ring_back)
    # the core sits inside the shell: draw it first so the glass faces and the
    # near (bright) shell edges pass over it, not under it
    s.append(core)
    s.append(faces)
    s.append(wire)
    s.append(verts)
    s.append(pulses)
    s.append(ring_front)
    s.append("</g>")

    # left column ----------------------------------------------------------
    # pill
    s.append(f'<g transform="translate(57 40)">'
             f'<rect width="186" height="34" rx="17" fill="{LIME}" fill-opacity=".08" '
             f'stroke="{LIME}" stroke-opacity=".38"/>'
             f'<circle class="ping" cx="19" cy="17" r="4.5" fill="{LIME}"/>'
             f'<circle cx="19" cy="17" r="4.5" fill="{LIME}"/>'
             f'<text x="34" y="23" font-family="{MONO}" font-size="17" fill="{LIME}" '
             f'textLength="134" lengthAdjust="spacingAndGlyphs">building metz</text></g>')
    # name with sheen + glitch
    s.append('<g class="nm">')
    s.append(f'<text class="glA" clip-path="url(#sliceA)" {name_attrs} fill="{CYAN}" opacity="0">zzqxck</text>')
    s.append(f'<text class="glB" clip-path="url(#sliceB)" {name_attrs} fill="{PINK}" opacity="0">zzqxck</text>')
    s.append(f'<text {name_attrs} fill="url(#nameBase)">zzqxck</text>')
    s.append(f'<text {name_attrs} fill="url(#sheen)">zzqxck</text>')
    s.append("</g>")
    s.append(f'<rect x="{NAME_X + NAME_LEN + 10}" y="{NAME_Y - 15}" width="15" height="15" fill="{LIME}"/>')
    # subtitle
    s.append(f'<text x="57" y="226" font-family="{SANS}" font-size="24" fill="{TEXT}" '
             f'letter-spacing=".2">full-stack dev<tspan fill="{LIME}"> · </tspan>'
             f'<tspan fill="{MUTED}">holon, il</tspan></text>')
    s.append(typing)

    # overlays
    s.append(f'<rect width="{W}" height="{H}" fill="url(#vig)"/>')
    s.append("</g>")
    s.append(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="21.5" fill="none" stroke="{HAIR}"/>')
    s.append("</svg>")
    return "\n".join(s)


def main():
    svg = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {OUT} ({len(svg.encode('utf-8')) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
