#!/usr/bin/env python3
"""Structurally diff a part in a generated .ms14 against a known-good donor part.

No Multisim, no simulation: pure XML shape comparison. Multisim crashes on malformed
element trees, so the cheapest test is "is this part isomorphic to a part the GUI
already saved?".

    python diff_part.py <generated.ms14> <refdes> <donor.xml> <refdes_in_donor>

Prints every tag-path + attribute key the donor has and the generated part lacks, plus
anything extra, and the same for the component's CiModel.
"""
import sys
import xml.etree.ElementTree as ET

import ms14


def load(path):
    if path.endswith(".ms14"):
        return ET.fromstring(ms14.unpack(path))
    return ET.parse(path).getroot()


def find_component(root, refdes):
    for c in root.iter("CiComponent"):
        if c.get("LocalName") == refdes:
            return c
    raise KeyError("no CiComponent %r" % refdes)


def symbol_for(root, comp):
    sid = comp.get("SymCompID")
    for objs in root.iter("Objects"):
        for o in objs:
            if o.get("ID") == sid:
                return o
    return None


def model_for(root, comp):
    mid = comp.get("Model")
    for it in root.iter("CiModel"):
        if it.get("CiID") == mid:
            return it
    return None


def shape(node, path="", out=None, texts=None):
    """Collect {tag-path: sorted attr keys} and {tag-path: text values}."""
    out = {} if out is None else out
    texts = {} if texts is None else texts
    tag = node.tag
    p = path + "/" + tag
    out.setdefault(p, set()).update(node.attrib)
    if (node.text or "").strip():
        texts.setdefault(p, set()).add(node.text.strip()[:40])
    for c in node:
        shape(c, p, out, texts)
    return out, texts


def compare(name, a_root, a_node, b_root, b_node):
    sa, ta = shape(a_node)
    sb, tb = shape(b_node)
    print("== %s" % name)
    for p in sorted(sb):
        if p not in sa:
            print("  MISSING node  %s" % p)
            continue
        miss = sb[p] - sa[p]
        if miss:
            print("  MISSING attrs %s: %s" % (p, ", ".join(sorted(miss))))
    for p in sorted(sa):
        if p not in sb:
            print("  EXTRA node    %s" % p)
    # per-path child counts (a symbol with different primitive counts is fine, but a
    # container that lost children is not)
    print("  nodes: generated=%d donor=%d" % (len(sa), len(sb)))


def main(argv):
    if len(argv) != 5:
        print(__doc__)
        return 2
    gen_root = load(argv[1])
    ref_root = load(argv[3])
    gc = find_component(gen_root, argv[2])
    rc = find_component(ref_root, argv[4])

    compare("component", gen_root, gc, ref_root, rc)
    gs, rs = symbol_for(gen_root, gc), symbol_for(ref_root, rc)
    compare("symbol", gen_root, gs, ref_root, rs)
    gm, rm = model_for(gen_root, gc), model_for(ref_root, rc)
    if gm is not None or rm is not None:
        compare("model", gen_root, gm, ref_root, rm)

    # pin-level sanity: every pin connector must point at an existing ConnectList id
    print("== pins")
    for label, root, comp in (("generated", gen_root, gc), ("donor", ref_root, rc)):
        sym = symbol_for(root, comp)
        pins = []
        for pe in sym.iter("CIITPinSymbolComp"):
            conn = pe.find(".//CIITPinConnectorComp/ConnectList/Item")
            pins.append((pe.get("PinName"), pe.get("PinNumber"), conn.get("ID") if conn is not None else None,
                         pe.get("PortID")))
        print("  %-9s %s" % (label, pins))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
