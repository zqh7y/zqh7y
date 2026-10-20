#!/usr/bin/env python3
"""Generate the social keycap buttons and the marquee footer.

Writes (deterministic, stdlib only):
  assets/btn-portfolio.svg  assets/btn-instagram.svg
  assets/btn-tiktok.svg     assets/btn-roblox.svg      (viewBox 220x56 each)
  assets/footer.svg                                    (viewBox 1000x90)

Run:  python3 src/buttons.py

Buttons
-------
Each button is a chunky keycap: an extruded body (the visible bottom edge,
holographic on the dark keys, deep lime on the primary key), a face with a
top bevel highlight, an icon tile, a label and a little "open" arrow.
Every PERIOD seconds the key does one "event": it presses down and springs
back, a holo/white shimmer sweeps across the face, the arrow slides out and
back in, and the icon does its own trick (the globe spins all the time, the
camera snaps, the tiktok note glitches, the roblox block quarter-turns).
Each button runs the same PERIOD with a different offset, so on the profile
the four keys fire in a left-to-right wave instead of flashing together.

The portfolio globe is real 3D: four half-meridians at 90 degree spacing are
rotated about the vertical axis and projected; each projected half-meridian is
a half-ellipse with signed semi-axis a = -R cos(phi), drawn as two cubics so
SMIL can interpolate the path. Back halves fade out using sin(phi).

Footer
------
A seamless marquee (each word/sparkle has an explicit textLength, so one
copy has an exact width W regardless of the viewer's fonts, and the strip
slides by exactly W per loop), two holographic sine waves drifting in
opposite directions underneath (each slides by exactly one wavelength per
loop), and a small credit line.
"""
import math
import os
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "assets")

# ---------------------------------------------------------------- palette
INK = "#0b0b0c"
PANEL = "#141416"
HAIR = "#26262b"
TEXT = "#f5f5f2"
MUTED = "#8a8a90"
LIME = "#d4ff3a"
LIME2 = "#b8f000"
CYAN, VIOLET, PINK = "#7af0ff", "#b48cff", "#ff8ad8"

SANS = "'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

# Arial / Helvetica advance widths (1/1000 em) - used to give every label an
# explicit textLength so layout never depends on the viewer's fonts.
_AB = dict(a=556, b=611, c=556, d=611, e=556, f=333, g=611, h=611, i=278,
           j=278, k=556, l=278, m=889, n=611, o=611, p=611, q=611, r=389,
           s=556, t=333, u=611, v=556, w=778, x=556, y=556, z=500)
_AB.update({" ": 278, ".": 278, "·": 278, "@": 975, "-": 333})
_AB.update({str(d): 556 for d in range(10)})


def w_bold(s, fs):
    return sum(_AB.get(ch, 600) for ch in s) * fs / 1000.0


def w_mono(s, fs):
    return len(s) * 0.6 * fs


def f(x, nd=2):
    """Compact number formatting."""
    s = f"{x:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ---------------------------------------------------------------- SMIL helpers
LIN = "0 0 1 1"
EIO = "0.45 0 0.55 1"      # ease in-out
EOUT = "0.2 0.8 0.3 1"     # ease out (snappy)
EIN = "0.6 0 0.9 0.6"      # ease in


def seq(period, offset, start, steps, end=None):
    """Build keyTimes/values/keySplines for a one-event-per-loop animation.

    The value rests at `start` until `offset`, then follows `steps`
    [(dt, value, spline), ...] and holds the last value until the loop ends.
    `end` (defaults to start) must equal the last step value; it may differ
    from `start` only when the two render identically (e.g. a 90 degree turn
    of a square), which keeps the loop seamless.
    """
    end = start if end is None else end
    ts, vs, sps = [0.0], [start], []
    t = offset
    if offset > 0:
        ts.append(offset)
        vs.append(start)
        sps.append(LIN)
    for dt, v, sp in steps:
        t += dt
        ts.append(t)
        vs.append(v)
        sps.append(sp)
    assert vs[-1] == end, (vs[-1], end)
    assert t < period - 0.05, "event must finish inside the loop"
    ts.append(period)
    vs.append(end)
    sps.append(LIN)
    kts = [x / period for x in ts]
    kts[0], kts[-1] = 0.0, 1.0
    return kts, vs, sps


def smil(tag, attr, period, kts, vals, sps=None, ttype=None, extra=""):
    a = [f'<{tag} attributeName="{attr}"']
    if ttype:
        a.append(f' type="{ttype}"')
    a.append(f' dur="{f(period, 3)}s" repeatCount="indefinite"')
    a.append(' keyTimes="' + ";".join(f(k, 4) for k in kts) + '"')
    a.append(' values="' + ";".join(str(v) for v in vals) + '"')
    if sps:
        a.append(' calcMode="spline" keySplines="' + ";".join(sps) + '"')
    a.append(extra + "/>")
    return "".join(a)


def loop_anim(tag, attr, dur, vals, ttype=None):
    """Evenly spaced linear loop (vals[0] must render the same as vals[-1])."""
    t = f' type="{ttype}"' if ttype else ""
    return (f'<{tag} attributeName="{attr}"{t} dur="{f(dur, 3)}s" '
            f'repeatCount="indefinite" values="' + ";".join(vals) + '"/>')


# ================================================================ BUTTONS
BW, BH = 220, 56
PERIOD = 6.0
FACE_X, FACE_Y, FACE_W, FACE_H, FACE_R = 4, 2, 212, 42, 14
BODY_Y, BODY_H = 8, 43          # body bottom = 51 -> 7px of visible depth
ICX, ICY = 26, 23               # icon centre
TILE = 30
LABEL_CX, LABEL_BASE, LABEL_FS = 115, 29.6, 20
ARROW_CX = 196
PRESS = 3.5


def globe_icon(color, dim_color):
    """Spinning wireframe globe: four half-meridians, rotating in 3D."""
    R = 8.6
    k = 0.5523
    spin = 8.0                       # seconds per full turn
    nstep = 36
    out = []
    # latitude lines + equator stop inside the ring (the ring is drawn last,
    # on top, so no line end pokes over the bright outline)
    lat = R * 0.5
    hl = R * math.cos(math.asin(0.5)) - 0.9
    out.append(f'<path d="M{f(-hl)} {f(-lat)}H{f(hl)}M{f(-hl)} {f(lat)}H{f(hl)}" '
               f'stroke="{dim_color}" stroke-width="1.1" stroke-linecap="round"/>')
    out.append(f'<path d="M{f(-R + 0.9)} 0H{f(R - 0.9)}" stroke="{color}" stroke-width="1.5" '
               f'stroke-linecap="round" opacity="0.9"/>')
    for m in range(4):
        ds, ops = [], []
        for i in range(nstep + 1):
            phi = math.radians(20 + 90 * m + 360.0 * i / nstep)
            a = -R * math.cos(phi)
            ds.append(f"M0 {f(-R)}C{f(k * a)} {f(-R)} {f(a)} {f(-k * R)} {f(a)} 0"
                      f"C{f(a)} {f(k * R)} {f(k * a)} {f(R)} 0 {f(R)}")
            front = math.sin(phi)
            ops.append(f(0.18 + 0.82 * (0.5 + 0.5 * front) ** 1.6, 3))
        out.append(f'<path fill="none" stroke="{color}" stroke-width="1.6" d="{ds[0]}" '
                   f'opacity="{ops[0]}">'
                   + loop_anim("animate", "d", spin, ds)
                   + loop_anim("animate", "opacity", spin, ops) + "</path>")
    out.append(f'<circle r="{R}" fill="none" stroke="{color}" stroke-width="1.8"/>')
    return "".join(out)


def camera_icon(offset):
    """Instagram-ish camera: holo outline, lens snaps like an aperture."""
    o = offset + 0.06
    kts, vs, sps = seq(PERIOD, o, "4.3", [
        (0.12, "2.3", EIN), (0.16, "5", EOUT), (0.22, "4.3", EIO)])
    lens = smil("animate", "r", PERIOD, kts, vs, sps)
    kts, vs, sps = seq(PERIOD, o + 0.1, "0", [
        (0.06, "0.55", EOUT), (0.45, "0", EIO)])
    flash = smil("animate", "opacity", PERIOD, kts, vs, sps)
    return (
        f'<rect x="-15" y="-15" width="30" height="30" rx="9" fill="#fff" opacity="0">'
        f'{flash}</rect>'
        f'<rect x="-8.6" y="-8.6" width="17.2" height="17.2" rx="5.4" fill="none" '
        f'stroke="url(#ig)" stroke-width="2"/>'
        f'<circle r="4.3" fill="none" stroke="url(#ig)" stroke-width="2">{lens}</circle>'
        f'<circle cx="4.75" cy="-4.75" r="1.25" fill="url(#ig)"/>'
    )


NOTE_D = ("M-2.6 4.6m-3.9 0a3.9 3.9 0 1 0 7.8 0a3.9 3.9 0 1 0 -7.8 0"
          "M1.3 4.6V-8.4C1.9 -5.2 4.4 -3.4 7.4 -3.4")


def note_icon(offset):
    """TikTok-ish note with cyan/pink chromatic split that glitches."""
    o = offset + 0.06
    base = 1.1

    def split(sign):
        b = f"{f(sign * -base)} {f(sign * -base * 0.8)}"
        steps = [(0.07, f"{f(sign * -2.8)} {f(sign * -1.4)}", EOUT),
                 (0.07, f"{f(sign * 1.6)} {f(sign * -0.4)}", LIN),
                 (0.07, f"{f(sign * -2.2)} {f(sign * -2.0)}", LIN),
                 (0.30, b, EIO)]
        kts, vs, sps = seq(PERIOD, o, b, steps)
        return smil("animateTransform", "transform", PERIOD, kts, vs, sps, "translate")

    kts, vs, sps = seq(PERIOD, o, "0 0", [
        (0.14, "0 -2.4", EOUT), (0.3, "0 0", EIO)])
    hop = smil("animateTransform", "transform", PERIOD, kts, vs, sps, "translate")
    common = 'fill="none" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"'
    return (
        f'<g transform="translate(-0.4 0)"><g>{hop}'
        f'<g><path d="{NOTE_D}" stroke="{CYAN}" {common}/>{split(1)}</g>'
        f'<g><path d="{NOTE_D}" stroke="{PINK}" {common}/>{split(-1)}</g>'
        f'<path d="{NOTE_D}" stroke="{TEXT}" {common}/>'
        f'</g></g>'
    )


def block_icon(offset):
    """Roblox-ish tilted block with a square hole; quarter-turns each loop."""
    o = offset + 0.06
    s, hole = 7.0, 2.1
    d = (f"M{-s} {-s}H{s}V{s}H{-s}Z"
         f"M{-hole} {-hole}V{hole}H{hole}V{-hole}Z")
    kts, vs, sps = seq(PERIOD, o, "15", [
        (0.38, "113", EIO), (0.2, "105", EOUT)], end="105")
    spin = smil("animateTransform", "transform", PERIOD, kts, vs, sps, "rotate")
    # The face gradient is in the rotating path's user space; counter-rotate it
    # on the same timeline so the light stays fixed on screen. Otherwise the
    # 105 -> 15 degree wrap at the loop point would snap the shading direction.
    counter = smil("animateTransform", "gradientTransform", PERIOD, kts,
                   [str(-int(v)) for v in vs], sps, "rotate")
    layers = []
    n = 5
    for i in range(n, 0, -1):          # fake extrusion: stacked copies
        t = i / n
        shade = int(0x3a + (0x6a - 0x3a) * (1 - t))
        col = f"#{shade:02x}{shade:02x}{shade + 6:02x}"
        layers.append(
            f'<g transform="translate({f(0.5 * t)} {f(2.4 * t)})"><path d="{d}" fill="{col}" '
            f'fill-rule="evenodd" transform="rotate(15)">{spin}</path></g>')
    layers.append(f'<path d="{d}" fill="url(#blk)" fill-rule="evenodd" '
                  f'transform="rotate(15)">{spin}</path>')
    return ('<g transform="translate(0 -1)">' + "".join(layers) + "</g>"), counter


def button(name, label, primary, offset):
    P = PERIOD
    o = offset
    lw = w_bold(label, LABEL_FS)

    if primary:
        face_top, face_bot = "#e6ff7a", "#c4f01a"
        label_col, arrow_col = INK, INK
        tile_fill, tile_stroke = INK, "none"
    else:
        face_top, face_bot = "#25252b", "#141417"
        label_col, arrow_col = TEXT, MUTED
        tile_fill, tile_stroke = INK, "#2f2f36"

    defs = []
    defs.append(
        '<filter id="soft" x="-30%" y="-150%" width="160%" height="400%">'
        '<feGaussianBlur stdDeviation="2.6"/></filter>')
    defs.append(
        f'<linearGradient id="face" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{face_top}"/>'
        f'<stop offset="1" stop-color="{face_bot}"/></linearGradient>')
    hl_top = "0.75" if primary else "0.28"
    defs.append(
        f'<linearGradient id="bevel" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#fff" stop-opacity="{hl_top}"/>'
        f'<stop offset="0.3" stop-color="#fff" stop-opacity="0.04"/>'
        f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    dish = (("#5d7a00", "0.16", "#ffffff", "0.22") if primary
            else ("#000000", "0.28", "#ffffff", "0.05"))
    defs.append(
        f'<linearGradient id="dish" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{dish[0]}" stop-opacity="{dish[1]}"/>'
        f'<stop offset="0.55" stop-color="{dish[0]}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{dish[2]}" stop-opacity="{dish[3]}"/></linearGradient>')
    if primary:
        defs.append(
            '<linearGradient id="side" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0.75" stop-color="#9dc80a"/>'
            '<stop offset="1" stop-color="#5f7a00"/></linearGradient>')
    else:
        # holographic edge that drifts sideways (repeat-spread, slides by one
        # full gradient period per loop -> seamless)
        defs.append(
            f'<linearGradient id="holo" gradientUnits="userSpaceOnUse" x1="0" y1="0" '
            f'x2="{BW}" y2="0" spreadMethod="repeat">'
            f'<stop offset="0" stop-color="{CYAN}"/><stop offset="0.33" stop-color="{VIOLET}"/>'
            f'<stop offset="0.66" stop-color="{PINK}"/><stop offset="1" stop-color="{CYAN}"/>'
            + loop_anim("animateTransform", "gradientTransform", 9.0,
                        ["translate(0 0)", f"translate({BW} 0)"], "translate")
            + '</linearGradient>')
        defs.append(
            '<linearGradient id="shade" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0.82" stop-color="#000" stop-opacity="0.12"/>'
            '<stop offset="0.93" stop-color="#000" stop-opacity="0.38"/>'
            '<stop offset="1" stop-color="#000" stop-opacity="0.72"/></linearGradient>')
    # shimmer band
    if primary:
        shim = [("0", "#fff", 0), ("0.42", "#fff", 0.35), ("0.5", "#fff", 0.75),
                ("0.58", "#fff", 0.35), ("1", "#fff", 0)]
    else:
        shim = [("0", CYAN, 0), ("0.3", CYAN, 0.22), ("0.5", "#ffffff", 0.36),
                ("0.7", PINK, 0.22), ("1", PINK, 0)]
    defs.append('<linearGradient id="shim" x1="0" y1="0" x2="1" y2="0">'
                + "".join(f'<stop offset="{a}" stop-color="{c}" stop-opacity="{op}"/>'
                          for a, c, op in shim) + '</linearGradient>')
    defs.append(f'<clipPath id="fc"><rect x="{FACE_X}" y="{FACE_Y}" width="{FACE_W}" '
                f'height="{FACE_H}" rx="{FACE_R}"/></clipPath>')
    defs.append(f'<clipPath id="ac"><rect x="{ARROW_CX - 10}" y="{ICY - 10}" '
                f'width="20" height="20"/></clipPath>')
    if name == "instagram":
        defs.append(
            f'<linearGradient id="ig" gradientUnits="userSpaceOnUse" x1="-9" y1="9" x2="9" y2="-9">'
            f'<stop offset="0" stop-color="{LIME}"/><stop offset="0.35" stop-color="{PINK}"/>'
            f'<stop offset="0.68" stop-color="{VIOLET}"/><stop offset="1" stop-color="{CYAN}"/>'
            f'</linearGradient>')
    if name == "roblox":
        block, block_counter = block_icon(o)
        defs.append(
            f'<linearGradient id="blk" gradientUnits="userSpaceOnUse" x1="0" y1="-8" x2="0" y2="8" '
            f'gradientTransform="rotate(-15)">'
            f'<stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#d9d9de"/>'
            f'{block_counter}</linearGradient>')

    # ---------------- press timeline (shared by face, shadow)
    kts, vs, sps = seq(P, o, "0 0", [
        (0.11, f"0 {PRESS}", EIN), (0.2, "0 -0.6", EOUT), (0.2, "0 0", EIO)])
    press = smil("animateTransform", "transform", P, kts, vs, sps, "translate")

    body = []
    # contact shadow / glow
    if primary:
        kts, vs, sps = seq(P, o, "0.5", [(0.11, "0.85", EIN), (0.6, "0.5", EIO)])
        glow_anim = smil("animate", "opacity", P, kts, vs, sps)
        body.append(f'<rect x="18" y="41" width="184" height="11" rx="5.5" fill="{LIME}" '
                    f'opacity="0.5" filter="url(#soft)">{glow_anim}</rect>')
    else:
        body.append('<rect x="16" y="42" width="188" height="10" rx="5" fill="#000" '
                    'opacity="0.55" filter="url(#soft)"/>')
    # extruded body (visible bottom depth)
    bx, bw = FACE_X, FACE_W
    if primary:
        body.append(f'<rect x="{bx}" y="{BODY_Y}" width="{bw}" height="{BODY_H}" rx="{FACE_R}" '
                    f'fill="url(#side)"/>')
    else:
        body.append(f'<rect x="{bx}" y="{BODY_Y}" width="{bw}" height="{BODY_H}" rx="{FACE_R}" '
                    f'fill="url(#holo)"/>')
        body.append(f'<rect x="{bx}" y="{BODY_Y}" width="{bw}" height="{BODY_H}" rx="{FACE_R}" '
                    f'fill="url(#shade)"/>')
    body.append(f'<rect x="{bx + 0.5}" y="{BODY_Y + 0.5}" width="{bw - 1}" height="{BODY_H - 1}" '
                f'rx="{FACE_R - 0.5}" fill="none" stroke="#000" stroke-opacity="0.35"/>')

    face = []
    face.append(f'<rect x="{FACE_X}" y="{FACE_Y}" width="{FACE_W}" height="{FACE_H}" '
                f'rx="{FACE_R}" fill="url(#face)"/>')
    # concave keycap "dish": slightly darker at the top, catching light at the bottom
    face.append(f'<rect x="{FACE_X + 4}" y="{FACE_Y + 3}" width="{FACE_W - 8}" '
                f'height="{FACE_H - 7}" rx="{FACE_R - 3}" fill="url(#dish)"/>')
    if not primary:
        face.append(f'<rect x="{FACE_X + 0.5}" y="{FACE_Y + 0.5}" width="{FACE_W - 1}" '
                    f'height="{FACE_H - 1}" rx="{FACE_R - 0.5}" fill="none" stroke="{HAIR}"/>')
    face.append(f'<rect x="{FACE_X + 0.5}" y="{FACE_Y + 0.5}" width="{FACE_W - 1}" '
                f'height="{FACE_H - 1}" rx="{FACE_R - 0.5}" fill="none" stroke="url(#bevel)"/>')
    # icon tile
    tx, ty = ICX - TILE / 2, ICY - TILE / 2
    stroke = f' stroke="{tile_stroke}"' if tile_stroke != "none" else ""
    face.append(f'<rect x="{f(tx + 0.5)}" y="{f(ty + 0.5)}" width="{TILE - 1}" height="{TILE - 1}" '
                f'rx="8.5" fill="{tile_fill}"{stroke}/>')
    if name == "portfolio":
        icon = globe_icon(LIME, "#7f9a22")
    elif name == "instagram":
        icon = camera_icon(o)
    elif name == "tiktok":
        icon = note_icon(o)
    else:
        icon = block
    face.append(f'<g transform="translate({ICX} {ICY})">{icon}</g>')
    # label
    face.append(f'<text x="{LABEL_CX}" y="{LABEL_BASE}" text-anchor="middle" '
                f'font-family="{SANS}" font-size="{LABEL_FS}" font-weight="700" '
                f'fill="{label_col}" textLength="{f(lw, 1)}" '
                f'lengthAdjust="spacingAndGlyphs">{label}</text>')
    # arrow: slides out top-right and comes back in from bottom-left
    kts, vs, sps = seq(P, o + 0.08, "0 0", [
        (0.22, "13 -13", EIN), (0.01, "-13 13", LIN), (0.42, "0 0", EOUT)])
    arrow_anim = smil("animateTransform", "transform", P, kts, vs, sps, "translate")
    face.append(
        f'<g clip-path="url(#ac)"><g transform="translate({ARROW_CX} {ICY})"><g>{arrow_anim}'
        f'<path d="M-4.4 4.4L4.4 -4.4M-2.6 -4.6H4.6V2.6" fill="none" stroke="{arrow_col}" '
        f'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></g></g></g>')
    # shimmer sweep across the face
    kts, vs, sps = seq(P, o + 0.04, "-30 0", [(1.0, "300 0", EIO)], end="300 0")
    # (start -30 and end 300 are both fully off-face, so the jump is invisible)
    sweep = smil("animateTransform", "transform", P, kts, vs, sps, "translate")
    face.append(
        f'<g clip-path="url(#fc)"><g transform="skewX(-22)">'
        f'<rect x="-60" y="-10" width="64" height="80" fill="url(#shim)">{sweep}</rect>'
        f'</g></g>')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{BW}" height="{BH}" '
        f'viewBox="0 0 {BW} {BH}" role="img" aria-label="{label}">'
        f'<title>{label}</title>'
        f'<defs>{"".join(defs)}</defs>'
        f'{"".join(body)}'
        f'<g>{press}{"".join(face)}</g>'
        f'</svg>\n')
    return svg


# ================================================================ FOOTER
FW, FH = 1000, 90
F_RX = 20
MQ_BASE = 39.5
CAT_FS = 30
TECH_FS = 25
SEP_GAP = 24
SPARK = 6.5
SPEED = 52.0                 # px / s


def sparkle(cx, cy, r, fill):
    k = r * 0.16
    return (f'<path transform="translate({f(cx)} {f(cy)})" fill="{fill}" '
            f'd="M0 {f(-r)}C{f(k)} {f(-k)} {f(k)} {f(-k)} {f(r)} 0'
            f'C{f(k)} {f(k)} {f(k)} {f(k)} 0 {f(r)}'
            f'C{f(-k)} {f(k)} {f(-k)} {f(k)} {f(-r)} 0'
            f'C{f(-k)} {f(-k)} {f(-k)} {f(-k)} 0 {f(-r)}Z"/>')


def marquee_strip():
    items = [("apps", "cat"), ("web", "cat"), ("games", "cat"), ("programs", "cat"),
             ("react native", "tech"), ("expo", "tech"), ("python", "tech"),
             ("luau", "tech"), ("three.js", "tech")]
    parts = []
    x = 0.0
    for word, kind in items:
        if kind == "cat":
            w = w_bold(word, CAT_FS)
            parts.append(
                f'<text x="{f(x)}" y="{MQ_BASE}" font-family="{SANS}" font-size="{CAT_FS}" '
                f'font-weight="800" fill="{LIME}" textLength="{f(w)}" '
                f'lengthAdjust="spacingAndGlyphs">{word}</text>')
        else:
            w = w_mono(word, TECH_FS)
            parts.append(
                f'<text x="{f(x)}" y="{MQ_BASE}" font-family="{MONO}" font-size="{TECH_FS}" '
                f'font-weight="500" fill="{MUTED}" textLength="{f(w)}" '
                f'lengthAdjust="spacingAndGlyphs">{word}</text>')
        x += w + SEP_GAP
        parts.append(sparkle(x + SPARK, MQ_BASE - 9.5, SPARK, "url(#holoS)"))
        x += 2 * SPARK + SEP_GAP
    return "".join(parts), x


def wave_path(cy, amp, lam, x0, x1, step=4.0):
    pts = []
    n = int(math.ceil((x1 - x0) / step))
    for i in range(n + 1):
        x = x0 + i * step
        y = cy + amp * math.sin(2 * math.pi * (x - x0) / lam)
        pts.append(f"{f(x, 1)} {f(y, 2)}")
    return "M" + "L".join(pts)


def footer():
    strip, W = marquee_strip()
    copies = int(math.ceil((FW + W) / W))   # enough to cover the panel at any shift
    mq_dur = W / SPEED
    strips = "".join(f'<g transform="translate({f(i * W)} 0)">{strip}</g>' for i in range(copies))
    mq_anim = loop_anim("animateTransform", "transform", mq_dur,
                        ["0 0", f"{f(-W)} 0"], "translate")

    # waves (each slides exactly one wavelength per loop)
    WY = 54.0
    lam1, lam2 = 250.0, 160.0
    w1 = wave_path(WY, 3.6, lam1, -lam1, FW + lam1)
    w2 = wave_path(WY, 2.4, lam2, -lam2, FW + lam2)
    a1 = loop_anim("animateTransform", "transform", 5.0, ["0 0", f"{f(lam1)} 0"], "translate")
    a2 = loop_anim("animateTransform", "transform", 4.0, ["0 0", f"{f(-lam2)} 0"], "translate")

    defs = []
    defs.append(
        f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#111113"/><stop offset="1" stop-color="{INK}"/>'
        f'</linearGradient>')
    defs.append(
        f'<clipPath id="panel"><rect width="{FW}" height="{FH}" rx="{F_RX}"/></clipPath>')
    # edge fade for the marquee
    defs.append(
        '<linearGradient id="fadeG" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset="0.09" stop-color="#fff" stop-opacity="1"/>'
        '<stop offset="0.91" stop-color="#fff" stop-opacity="1"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    defs.append(
        f'<mask id="fade" maskUnits="userSpaceOnUse" x="0" y="0" width="{FW}" height="{FH}">'
        f'<rect width="{FW}" height="{FH}" fill="url(#fadeG)"/></mask>')
    # holo gradient that drifts (repeat spread, slides one period per loop)
    defs.append(
        f'<linearGradient id="holoW" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="500" y2="0" '
        f'spreadMethod="repeat">'
        f'<stop offset="0" stop-color="{CYAN}"/><stop offset="0.3" stop-color="{VIOLET}"/>'
        f'<stop offset="0.55" stop-color="{PINK}"/><stop offset="0.8" stop-color="{LIME}"/>'
        f'<stop offset="1" stop-color="{CYAN}"/>'
        + loop_anim("animateTransform", "gradientTransform", 12.0,
                    ["translate(0 0)", "translate(500 0)"], "translate")
        + '</linearGradient>')
    defs.append(
        f'<linearGradient id="holoS" gradientUnits="userSpaceOnUse" x1="-6" y1="-6" x2="6" y2="6">'
        f'<stop offset="0" stop-color="{CYAN}"/><stop offset="0.5" stop-color="{VIOLET}"/>'
        f'<stop offset="1" stop-color="{PINK}"/></linearGradient>')
    defs.append(
        '<filter id="wblur" x="-5%" y="-200%" width="110%" height="500%">'
        '<feGaussianBlur stdDeviation="3"/></filter>')
    defs.append(
        f'<mask id="wave" maskUnits="userSpaceOnUse" x="0" y="0" width="{FW}" height="{FH}">'
        f'<g fill="none" stroke-linecap="round">'
        f'<g><path d="{w1}" stroke="#fff" stroke-width="1.8"/>{a1}</g>'
        f'<g><path d="{w2}" stroke="#fff" stroke-opacity="0.45" stroke-width="1.2"/>{a2}</g>'
        f'</g></mask>')
    defs.append(
        f'<mask id="waveGlow" maskUnits="userSpaceOnUse" x="0" y="0" width="{FW}" height="{FH}">'
        f'<g fill="none" filter="url(#wblur)">'
        f'<g><path d="{w1}" stroke="#fff" stroke-opacity="0.5" stroke-width="5"/>{a1}</g>'
        f'</g></mask>')
    defs.append(
        '<radialGradient id="dotG"><stop offset="0" stop-color="#d4ff3a" stop-opacity="0.6"/>'
        '<stop offset="1" stop-color="#d4ff3a" stop-opacity="0"/></radialGradient>')

    # credit line
    CB = 78.5
    CFS = 18                  # >= 7px even when the footer is shown 400px wide
    segs = [("made by ", MUTED), ("zzqxck", TEXT), (" · since ", MUTED), ("2022", LIME)]
    total = sum(w_mono(s, CFS) for s, _ in segs)
    cx0 = FW / 2 - total / 2 + 10
    credit = []
    x = cx0
    for s, col in segs:
        w = w_mono(s, CFS)
        credit.append(
            f'<text x="{f(x)}" y="{CB}" font-family="{MONO}" font-size="{CFS}" fill="{col}" '
            f'textLength="{f(w)}" lengthAdjust="spacingAndGlyphs" xml:space="preserve">{s}</text>')
        x += w
    dot_x = cx0 - 16
    dot_y = CB - 5.5
    pulse_r = loop_anim("animate", "r", 2.4, ["3", "9", "9"])
    pulse_o = loop_anim("animate", "opacity", 2.4, ["0.9", "0", "0"])
    credit.insert(0,
        f'<circle cx="{f(dot_x)}" cy="{dot_y}" r="3" fill="url(#dotG)" opacity="0.9">'
        f'{pulse_r}{pulse_o}</circle>'
        f'<circle cx="{f(dot_x)}" cy="{dot_y}" r="3" fill="{LIME}"/>')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{FW}" height="{FH}" '
        f'viewBox="0 0 {FW} {FH}" role="img" '
        f'aria-label="apps, web, games, programs, react native, expo, python, luau, three.js - made by zzqxck since 2022">'
        f'<title>made by zzqxck</title>'
        f'<defs>{"".join(defs)}</defs>'
        f'<g clip-path="url(#panel)">'
        f'<rect width="{FW}" height="{FH}" fill="url(#bg)"/>'
        f'<g mask="url(#fade)">'
        f'<rect width="{FW}" height="{FH}" fill="url(#holoW)" mask="url(#waveGlow)" opacity="0.9"/>'
        f'<rect width="{FW}" height="{FH}" fill="url(#holoW)" mask="url(#wave)"/></g>'
        f'<g mask="url(#fade)"><g>{mq_anim}{strips}</g></g>'
        f'{"".join(credit)}'
        f'</g>'
        f'<rect x="0.5" y="0.5" width="{FW - 1}" height="{FH - 1}" rx="{F_RX - 0.5}" fill="none" '
        f'stroke="{HAIR}"/>'
        f'</svg>\n')
    return svg, W, mq_dur


# ================================================================ main
FORBIDDEN = ("<script", "foreignObject", "onload", "onclick", "href", "http://www.w3.org/1999/xlink",
             "@import", "url(http", "url('http", 'url("http')


def check(path, text):
    ET.fromstring(text)
    body = text.replace('xmlns="http://www.w3.org/2000/svg"', "")
    for bad in FORBIDDEN:
        assert bad not in body, f"{path}: forbidden token {bad!r}"
    assert "http" not in body, f"{path}: external URL"
    assert len(text.encode()) < 250_000, f"{path}: too big"


def write(name, text):
    path = os.path.join(ASSETS, name)
    check(path, text)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote {os.path.relpath(path, os.path.join(HERE, '..'))}  {len(text.encode())} bytes")


def main():
    os.makedirs(ASSETS, exist_ok=True)
    buttons = [("portfolio", True), ("instagram", False), ("tiktok", False), ("roblox", False)]
    for i, (name, primary) in enumerate(buttons):
        write(f"btn-{name}.svg", button(name, name, primary, 0.3 + 0.45 * i))
    svg, W, dur = footer()
    write("footer.svg", svg)
    print(f"marquee strip width {W:.1f}px, loop {dur:.2f}s")


if __name__ == "__main__":
    main()
