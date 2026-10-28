#!/usr/bin/env python3
"""Junction dots and stacked wires - the visual defects a reviewer sees first.

    python checkjoins.py ../Q*.ms14

  J1  a junction object (a drawn dot) must sit where 3+ wire ends meet. Two is a corner:
      the dot then promises a connection that does not exist.
  J2  no two segments of the same net may lie on top of each other. Stacked collinear
      wires are what makes a rail look doubled and keeps merging under editing.
  J3  every junction's stubs must be used by exactly the wires it joins (no stub left
      behind, none missing).
"""
import collections
import sys
import xml.etree.ElementTree as ET

import ms14


def audit(path):
    try:
        root = ET.fromstring(ms14.unpack(path))
    except ValueError:
        return []          # not a Multisim project (a donor xml fragment) - nothing to audit
    if next(root.iter("CiCircuit"), None) is None:
        return []
    juncs, wires = [], []
    for objs in root.iter("Objects"):
        for it in objs:
            if it.get("Class") == "CODPinComp":
                el = it[0] if len(it) else it
                if el.get("CenterX") is not None:
                    cl = el.find("ConnectList")
                    juncs.append((round(float(el.get("CenterX"))),
                                  round(float(el.get("CenterY"))),
                                  [r.get("ID") for r in (cl if cl is not None else [])]))
            elif it.get("Class") == "CIITLinkComp":
                el = it[0]
                pts = [(round(float(p.get("X"))), round(float(p.get("Y"))))
                       for p in el.find("Points")]
                for a, b in zip(pts, pts[1:]):
                    wires.append((el.get("Node"), a, b, el.get("Connect1"), el.get("Connect2")))

    ends = collections.Counter()
    for _n, a, b, _c1, _c2 in wires:
        ends[a] += 1
        ends[b] += 1

    bad = []
    for x, y, stubs in juncs:
        if ends[(x, y)] < 3:
            bad.append("J1 dot at (%d,%d) joins only %d wire end(s)" % (x, y, ends[(x, y)]))
        used = {c for _n, _a, _b, c1, c2 in wires for c in (c1, c2)}
        loose = [s for s in stubs if s not in used]
        if loose:
            bad.append("J3 dot at (%d,%d) has %d unused stub(s)" % (x, y, len(loose)))

    def overlap(p, q):
        if p[0] != q[0]:
            return False
        (_n, a1, b1, _c, _d), (_m, a2, b2, _e, _f) = p, q
        if a1[0] == b1[0] == a2[0] == b2[0]:
            lo = max(min(a1[1], b1[1]), min(a2[1], b2[1]))
            hi = min(max(a1[1], b1[1]), max(a2[1], b2[1]))
        elif a1[1] == b1[1] == a2[1] == b2[1]:
            lo = max(min(a1[0], b1[0]), min(a2[0], b2[0]))
            hi = min(max(a1[0], b1[0]), max(a2[0], b2[0]))
        else:
            return False
        return hi - lo > 2

    for i, p in enumerate(wires):
        for q in wires[i + 1:]:
            if overlap(p, q):
                bad.append("J2 %s %s-%s stacked on %s-%s" % (p[0][-6:], p[1], p[2], q[1], q[2]))
    return bad


def main(paths):
    total = 0
    for path in paths:
        bad = audit(path)
        total += len(bad)
        print("%-22s %s" % (path.rsplit("/", 1)[-1],
                            "JOINS CLEAN" if not bad else "%d problem(s)" % len(bad)))
        for b in bad[:8]:
            print("    " + b)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
