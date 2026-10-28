#!/usr/bin/env python3
"""Report where each voltmeter sits and whether its two leads stay apart.

    python checkmeters.py ../Q*.ms14

For every XMM: bbox, whether the ground rail runs below it, and which way the lead from
pin 1 (+ , the LEFT pin) leaves. Leaving to the right is the one geometry that reads as a
short, because that lead has to cross pin 2's own return lead to get there.
"""
import sys

import preview


def main(paths):
    for path in paths:
        parts, wires, _juncs, _pins, _labels = preview.model(path)
        name = path.rsplit("/", 1)[-1]
        for ref, bb, own in parts:
            if not ref.startswith("XMM"):
                continue
            pins = sorted(own)
            left = min(pins, key=lambda p: p[0])
            leads = [(a, b) for a, b in wires
                     if (abs(a[0] - left[0]) <= 2 and abs(a[1] - left[1]) <= 2)]
            first = []
            for a, b in leads:
                other = b if (abs(a[0] - left[0]) <= 2 and abs(a[1] - left[1]) <= 2) else a
                first.append(other)
            right = any(p[0] > left[0] + 2 for p in first)
            rail_below = any(abs(a[1] - b[1]) < 1 and a[1] > bb[3]
                             and min(a[0], b[0]) <= left[0] <= max(a[0], b[0])
                             for a, b in wires)
            # does any wire cross the return lead (pin 2) without terminating on it?
            other = [p for p in pins if p is not left][0]
            stub = [(a, b) for a, b in wires
                    if (abs(a[0] - other[0]) <= 2 and abs(a[1] - other[1]) <= 2)
                    or (abs(b[0] - other[0]) <= 2 and abs(b[1] - other[1]) <= 2)]
            clash = False
            for s0, s1 in wires:
                for t0, t1 in stub:
                    if (s0, s1) in leads or (s0, s1) == (t0, t1):
                        continue
                    if abs(t0[0] - t1[0]) < 1:            # stub is vertical
                        x = t0[0]
                        y0, y1 = sorted((t0[1], t1[1]))
                        a0, a1 = sorted((s0[0], s1[0]))
                        if abs(s0[1] - s1[1]) < 1 and a0 <= x <= a1 and y0 < s0[1] < y1:
                            clash = True
            print("%-18s %-5s bbox=%-24s pin1=%-14s lead=%-28s rail_below=%-5s %s" % (
                name, ref, [round(v) for v in bb], tuple(map(round, left)),
                [tuple(map(round, p)) for p in first], rail_below,
                ("RIGHT-LEAD " if right else "") + ("RETURN-CROSSED" if clash else "")))


if __name__ == "__main__":
    main(sys.argv[1:])
