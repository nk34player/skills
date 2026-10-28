#!/usr/bin/env python3
"""Which net each voltmeter terminal actually lands on.

    python checkmeterroles.py ../Q*.ms14

Prints `<refdes> + -> <net>  - -> <net>` and fails unless pin 1 sits on the intended
node and pin 2 on net `0` (a voltmeter reads V(node) with respect to its own -).
"""
import sys
import xml.etree.ElementTree as ET

import ms14

# refdes -> the node it must measure (README "Expected simulation results")
EXPECT = {
    "Q1_RTL_OR3": {"XMM1": "Y", "XMM2": "X"},
    "Q2_TTL_AND2": {"XMM1": "Y", "XMM2": "X"},
    "Q3_CMOS_NOR3": {"XMM1": "Y", "XMM2": "PP1"},
    "Q3_TG_OR3": {"XMM1": "Y", "XMM2": "Y1"},
}


def binding(path):
    """Instrument properties are keyed "&ASC<refdes>#1/Project:" and only bind when that
    stem equals the component's LocalName - a bare name orphans the block and the meter
    silently keeps its default 0 V display."""
    root = ET.fromstring(ms14.unpack(path))
    names = {(it[0].get("LocalName") or "")
             for it in next(root.iter("CIITDiagram")).find("Elements")
             if it.get("Class") == "CiComponent"}
    return [n.get("CompLongName") or "" for n in root.iter("CSourceSymbolCollectNode")
            if (n.get("CompLongName") or "").split("#")[0] not in names]


def roles(path):
    root = ET.fromstring(ms14.unpack(path))
    dia = next(root.iter("CIITDiagram"))
    comp = {it.get("CiID"): (it[0].get("LocalName") or "").replace("&ASC", "")
            for it in dia.find("Elements") if it.get("Class") == "CiComponent"}
    port = {}
    for it in root.iter("Item"):
        if it.get("Class") != "CiPort":
            continue
        e = it[0] if len(it) else it
        port[it.get("CiID")] = (comp.get(e.get("Component"), "?"),
                                (e.get("LocalName") or "").replace("&ASC", ""))
    out = {}
    for it in dia.find("Elements"):
        if it.get("Class") != "CiNode":
            continue
        name = (it[0].get("LocalName") or "").replace("&ASC", "")
        for r in it[0].find("Ports"):
            ref, pin = port.get(r.get("CiID"), (None, None))
            if ref and ref.startswith("XMM"):
                out[(ref, pin)] = name
    return out


def main(paths):
    bad = 0
    for path in paths:
        stem = path.rsplit("/", 1)[-1].split(".")[0]
        want = EXPECT.get(stem, {})
        got = roles(path)
        msgs = []
        orphan = binding(path)
        if orphan:
            bad += 1
            msgs.append("UNBOUND %s" % orphan)
        for ref in sorted({k[0] for k in got}):
            plus, minus = got.get((ref, "1")), got.get((ref, "2"))
            ok = plus == want.get(ref, plus) and minus == "0"
            bad += 0 if ok else 1
            msgs.append("%s + -> %-5s - -> %-3s%s" % (ref, plus, minus, "" if ok else "  WRONG"))
        print("%-20s %s" % (stem, "  |  ".join(msgs)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
