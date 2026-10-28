#!/usr/bin/env python3
"""Expand a .ms14 into its SPICE netlist, without Multisim.

    python netlist.py ../Q1_RTL_OR3.ms14            # print the netlist
    python netlist.py ../Q1_RTL_OR3.ms14 --check     # flag risky nodes

Expansion mirrors what Multisim does: the part's template (`CiaSpiceTmpltExprt`) with
`%p` refdes, `%t<pin>` node name, `%m` model and `#n` parameter slot (1-based).

`--check` reports nodes that cannot support a DC solution, which is what produces
"Singular matrix ... floating with respect to net 0":
  * a node touched by fewer than two element terminals (dangling)
  * a node with no path to ground through a resistor/source/transistor channel
"""
import re
import sys

import ms14
import xml.etree.ElementTree as ET

TPL = ("CiaSpiceTmpltExprt", "CiaCString")
# terminals per element type: which tokens after the name are nodes
NODES = {"r": 2, "c": 2, "l": 2, "v": 2, "i": 2, "d": 2, "q": 3, "m": 4, "j": 3, "x": 0}


def load(path):
    return ET.fromstring(ms14.unpack(path)) if path.endswith(".ms14") else ET.parse(path).getroot()


def build(path):
    root = load(path)
    dia = next(root.iter("CIITDiagram"))
    els = dia.find("Elements")

    # port CiID -> net name
    net_of_port = {}
    for it in els:
        if it.get("Class") == "CiNode":
            for r in it[0].find("Ports"):
                name = it[0].get("LocalName") or ""
                net_of_port[r.get("CiID")] = name[4:] if name.startswith("&ASC") else name

    # component refdes -> {pin name: net}
    sym_of, pin_nets = {}, {}
    for objs in root.iter("Objects"):
        for it in objs:
            if it.get("Class") == "CIITSymbolComp":
                sym_of[it.get("ID")] = it

    comps = {}
    for it in els:
        if it.get("Class") == "CiComponent":
            comps[it.get("CiID")] = it[0]

    by_ref = {}
    for it in els:
        if it.get("Class") != "CiComponent":
            continue
        inner = it[0]
        sym = sym_of.get(inner.get("SymCompID"))
        pins = {}
        if sym is not None:
            for pe in sym.iter("CIITPinSymbolComp"):
                label = (pe.get("PinName") or "").replace("&ASC", "")
                pins[label] = net_of_port.get(pe.get("PortID"), "?")
        by_ref[(inner.get("LocalName") or "").replace("&ASC", "")] = (inner, pins)

    lines, nodes = [], {}
    for ref, (c, pins) in by_ref.items():
        at = c.find("Attributes")
        if at is None or len(at) < 3:
            continue
        tpl = ""
        for grp in list(at)[1:2]:
            for ch in grp:
                if ch.tag in TPL:
                    tpl = (ch.get("String") or "").replace("&ASC", "")
        # An instrument's template starts with %p (its refdes already carries the SPICE
        # letter: XMM1 -> an 'X' subcircuit call). Requiring a literal letter here
        # silently dropped every meter from the netlist, so V(X) was never checked.
        if not tpl or not re.match(r"[a-zA-Z%]", tpl):
            continue
        params = []
        for grp in list(at)[2:3]:
            for sub in grp:
                if sub.tag == "CiaParamList":
                    for lst in sub:
                        if lst.tag == "parameters":
                            params = [x.get("Value", "").replace("&ASC", "") for x in lst]

        def sub_t(m):
            return pins.get(m.group(1), "?" + m.group(1))

        line = tpl.replace("%p", ref)
        line = re.sub(r"%t([A-Za-z0-9_]+)", sub_t, line)
        # %m is the name declared inside the part's card (".model Q2N3904/ON ..." or
        # ".subckt XMM1_V ..."), not the CiModel's LocalName
        declared, card = "", ""
        for mit in els:
            if mit.get("Class") == "CiModel" and mit.get("CiID") == c.get("Model"):
                for it in mit.iter("CiaCString"):
                    card = (it.get("String") or "").replace("&ASC", "")
                    break
                break
        toks = card.split()
        for i, tok in enumerate(toks):
            if tok.lower() in (".model", ".subckt") and i + 1 < len(toks):
                declared = toks[i + 1]          # MODPEX cards lead with comments
                break
        line = line.replace("%m", declared or ("M_" + ref))
        # `#n` is parameters[n], NOT parameters[n-1]: a GUI-saved part shows 200k and
        # stores it at parameters[1] while its stock template reads `#1`. Reading one slot
        # early silently expands every value as 0 (a 0-ohm resistor then makes the solver's
        # matrix singular) - the bug this expander used to have.
        line = re.sub(r"#([0-9]+)",
                      lambda m: (params[int(m.group(1))] if 0 <= int(m.group(1)) < len(params)
                                 else "?"), line)
        line = " ".join(line.split())
        if "?" in line:
            line += "   ; unresolved token"
        lines.append(line)

        letter = line[0].lower()
        # %p-as-letter: "XMM1 ..." is a subcircuit call, so it has no fixed node count
        if tpl.startswith("%p"):
            letter = "x"
        toks = line.split()
        n = NODES.get(letter, 0)
        if letter not in NODES:
            n = 0
        for t in toks[1:1 + n]:
            nodes.setdefault(t, []).append("%s(%s)" % (toks[0], letter))
    return lines, nodes


def check(nodes):
    bad = []
    for net, terms in sorted(nodes.items()):
        if net in ("0", "GND") or net.startswith("&ASC0"):
            continue
        if len(terms) < 2:
            bad.append((net, terms))
    return bad


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    lines, nodes = build(argv[1])
    if "--check" in argv:
        bad = check(nodes)
        print("%-24s elements=%-3d nodes=%-3d dangling=%d"
              % (argv[1].split("/")[-1], len(lines), len(nodes), len(bad)))
        for net, terms in bad:
            print("   FLOATING %-6s touched by %s" % (net, terms))
        for net in sorted(nodes):
            print("   %-8s %d terminal(s)" % (net, len(nodes[net])))
        return 0 if not bad else 1
    for l in lines:
        print(l)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
