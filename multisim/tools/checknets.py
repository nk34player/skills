#!/usr/bin/env python3
"""Fail if two different nets share a wire end / junction point (a silent short).

    python checknets.py ../Q*.ms14
"""
import collections
import sys
import xml.etree.ElementTree as ET

import ms14


def shared_points(path):
    root = ET.fromstring(ms14.unpack(path))
    dia = next(root.iter("CIITDiagram"))
    names = {it.get("CiID"): (it[0].get("LocalName") or "").replace("&ASC", "")
             for it in dia.find("Elements") if it.get("Class") == "CiNode"}
    pt = collections.defaultdict(set)
    for objs in root.iter("Objects"):
        for it in objs:
            if it.get("Class") != "CIITLinkComp":
                continue
            el = it[0]
            net = names.get(el.get("Node"), "?")
            for p in el.find("Points"):
                pt[(round(float(p.get("X"))), round(float(p.get("Y"))))].add(net)
    return [(p, sorted(s)) for p, s in pt.items() if len(s) > 1]


def main(paths):
    bad = 0
    for path in paths:
        shared = shared_points(path)
        bad += len(shared)
        print("%-22s %s" % (path.rsplit("/", 1)[-1],
                            "OK" if not shared else "SHORTED: %s" % shared))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
