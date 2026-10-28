#!/usr/bin/env python3
"""Render a .ms14 to PNG and measure wire/part overlap. No Multisim needed.

    python preview.py ../Q3_TG_OR3.ms14 [-o out.png] [--overlap]

The drawing is a schematic sketch, not a Multisim screenshot: part boxes, pins, wire
segments and junctions, drawn in page coordinates (1/1000 inch). `--overlap` prints the
number of wire segments that pass through a part body - the metric the router must keep
at zero.
"""
import sys

import ms14
import xml.etree.ElementTree as ET

PAGE_W, PAGE_H = 960, 720


def load(path):
    return ET.fromstring(ms14.unpack(path)) if path.endswith(".ms14") else ET.parse(path).getroot()


def model(path):
    """(parts, wires, junctions, nodes) in page coordinates."""
    root = load(path)
    dia = next(root.iter("CIITDiagram"))
    els = dia.find("Elements")

    sym_of = {}
    for objs in root.iter("Objects"):
        for it in objs:
            if it.get("Class") == "CIITSymbolComp":
                sym_of[it.get("ID")] = it

    parts, pins = [], []
    for it in els:
        if it.get("Class") != "CiComponent":
            continue
        inner = it[0]
        ref = (inner.get("LocalName") or "").replace("&ASC", "")
        sym = sym_of.get(inner.get("SymCompID"))
        if sym is None:
            continue
        sx = float(sym[0].get("Transformer-M20") or 0)
        sy = float(sym[0].get("Transformer-M21") or 0)
        xs, ys = [], []
        for el in sym.iter():
            if el.get("pt0X") is not None:
                xs += [sx + float(el.get("pt0X")), sx + float(el.get("pt1X") or 0)]
                ys += [sy + float(el.get("pt0Y")), sy + float(el.get("pt1Y") or 0)]
            if el.get("CenterX") is not None:
                r = float(el.get("Radius1") or 0)
                xs += [sx + float(el.get("CenterX")) - r, sx + float(el.get("CenterX")) + r]
                ys += [sy + float(el.get("CenterY")) - r, sy + float(el.get("CenterY")) + r]
        own = []
        for conn in sym.iter("CIITPinConnectorComp"):
            px, py = sx + float(conn.get("ptCenterX") or 0), sy + float(conn.get("ptCenterY") or 0)
            xs.append(px)
            ys.append(py)
            pins.append((px, py))
            own.append((px, py))
        if xs:
            parts.append((ref, (min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3), own))

    wires, juncs, labels = [], [], []
    for objs in root.iter("Objects"):
        for it in objs:
            if it.get("Class") == "CIITLinkComp":
                pts_el = it[0].find("Points")
                pts = [(float(p.get("X")), float(p.get("Y")))
                       for p in (pts_el if pts_el is not None else [])]
                for a, b in zip(pts, pts[1:]):
                    wires.append((a, b))
            elif it.get("Class") == "CODPinComp" and it[0].find("ConnectList") is not None:
                juncs.append((float(it[0].get("CenterX") or 0), float(it[0].get("CenterY") or 0)))
            elif it.get("Class") == "CODNodeTextComp":
                mx = float(it[0].get("Transformer-M20") or 0)
                my = float(it[0].get("Transformer-M21") or 0)
                labels.append((mx, my))
    return parts, wires, juncs, pins, labels


def floating(parts, wires, juncs, labels=(), tol=2.0):
    """Wire endpoints that end in empty space.

    An endpoint must be on a pin, on a junction, or shared with another segment. One that
    is not means a segment went missing - the net looks connected in the file but is open
    on the sheet (and simulates open too).
    """
    pins = [pin for _ref, _bb, own in parts for pin in own]
    # labels are stored 20 units off the wire end; accept both the raw and shifted spot
    jpts = [(x, y) for x, y in juncs] + list(labels) + [(x - 20, y - 20) for x, y in labels]

    def near(pt, others):
        return any(abs(pt[0] - q[0]) <= tol and abs(pt[1] - q[1]) <= tol for q in others)

    def on_segment(pt, a, b):
        """T-joints: real projects often land an endpoint on another wire's interior."""
        if abs(a[0] - b[0]) <= tol:                 # vertical
            return (abs(pt[0] - a[0]) <= tol
                    and min(a[1], b[1]) - tol <= pt[1] <= max(a[1], b[1]) + tol)
        if abs(a[1] - b[1]) <= tol:                 # horizontal
            return (abs(pt[1] - a[1]) <= tol
                    and min(a[0], b[0]) - tol <= pt[0] <= max(a[0], b[0]) + tol)
        return False

    ends = [a for a, b in wires] + [b for a, b in wires]
    bad = []
    for a, b in wires:
        for pt in (a, b):
            shared = sum(1 for e in ends if near(pt, [e])) > 1
            touched = near(pt, pins) or near(pt, jpts)
            if not touched:
                touched = any(on_segment(pt, p, q) for p, q in wires if (p, q) != (a, b))
            if shared or touched:
                continue
            bad.append((pt, a, b))
    return bad


def part_overlaps(parts, tol=2.0):
    """Pairs of parts whose bodies overlap (instruments landing on a symbol, say)."""
    bad = []
    for i in range(len(parts)):
        r1, (a0, b0, a1, b1), _ = parts[i]
        for j in range(i + 1, len(parts)):
            r2, (c0, d0, c1, d1), _ = parts[j]
            if a1 - tol <= c0 or a0 + tol >= c1 or b1 - tol <= d0 or b0 + tol >= d1:
                continue
            bad.append((r1, r2))
    return bad


def pin_short(parts, wires, tol=3.0):
    """Wires that pass through a pin they are not terminating on (an accidental short)."""
    bad = []
    for a, b in wires:
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        for ref, _bb, own in parts:
            for pin in own:
                if not (x0 - tol <= pin[0] <= x1 + tol and y0 - tol <= pin[1] <= y1 + tol):
                    continue
                if (abs(pin[0] - a[0]) <= tol and abs(pin[1] - a[1]) <= tol) or                    (abs(pin[0] - b[0]) <= tol and abs(pin[1] - b[1]) <= tol):
                    continue                     # legitimate termination
                bad.append((ref, pin, a, b))
    return bad


def overlaps(parts, wires, tol=3.0):
    """Wire segments crossing a part body that they do not legitimately attach to."""
    def on(pin, pt):
        return abs(pin[0] - pt[0]) <= tol and abs(pin[1] - pt[1]) <= tol

    bad = []
    for a, b in wires:
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        for ref, (bx0, by0, bx1, by1), own in parts:
            if x1 <= bx0 or x0 >= bx1 or y1 <= by0 or y0 >= by1:
                continue
            if any(on(pin, a) or on(pin, b) for pin in own):
                continue                       # this wire starts/ends on that part
            bad.append((ref, a, b))
    return bad


def draw(path, out):
    from PIL import Image, ImageDraw
    parts, wires, juncs, pins, labels = model(path)
    sc = 1.0
    img = Image.new("RGB", (int(PAGE_W * sc), int(PAGE_H * sc)), "white")
    d = ImageDraw.Draw(img)
    for _, (x0, y0, x1, y1), _own in parts:
        d.rectangle([x0 * sc, y0 * sc, x1 * sc, y1 * sc], outline=(200, 200, 255))
    for a, b in wires:
        d.line([a[0] * sc, a[1] * sc, b[0] * sc, b[1] * sc], fill=(0, 120, 0), width=1)
    for x, y in juncs:
        d.ellipse([x * sc - 3, y * sc - 3, x * sc + 3, y * sc + 3], fill=(200, 0, 0))
    for x, y in pins:
        d.ellipse([x * sc - 2, y * sc - 2, x * sc + 2, y * sc + 2], fill=(0, 0, 0))
    img.save(out)
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = argv[1]
    out = argv[argv.index("-o") + 1] if "-o" in argv else path.rsplit(".", 1)[0] + ".png"
    parts, wires, juncs, pins, labels = model(path)
    bad = overlaps(parts, wires)
    shorts = pin_short(parts, wires)
    opens = floating(parts, wires, juncs, labels)
    stacked = part_overlaps(parts)
    print("%-22s parts=%-3d wires=%-4d joints=%-4d cross=%-3d shorts=%-3d open=%-3d stack=%-2d %s"
          % (path.rsplit("/", 1)[-1], len(parts), len(wires), len(juncs), len(bad),
             len(shorts), len(opens), len(stacked),
             "CLEAN" if not bad and not shorts and not opens and not stacked else "PROBLEM"))
    for pt, a, b in opens[:6]:
        print("   OPEN endpoint (%.0f,%.0f) of (%.0f,%.0f)-(%.0f,%.0f)"
              % (pt[0], pt[1], a[0], a[1], b[0], b[1]))
    for ref, pin, a, b in shorts[:6]:
        print("   SHORT %s pin (%.0f,%.0f) crossed by (%.0f,%.0f)-(%.0f,%.0f)"
              % (ref, pin[0], pin[1], a[0], a[1], b[0], b[1]))
    if "--overlap" in argv:
        for ref, a, b in bad[:20]:
            print("   %s: (%.0f,%.0f)-(%.0f,%.0f)" % (ref, a[0], a[1], b[0], b[1]))
    if "--no-png" not in argv:
        print("   ->", draw(path, out))
    return 0 if not bad and not shorts and not opens and not stacked else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
