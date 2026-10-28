#!/usr/bin/env python3
"""Offline truth table: DC operating point of a generated sheet for each input state.

    python truthtable.py ../Q2_TTL_AND2.ms14 --in vV2 vV3 --out X Y

--in   voltage-source element names that drive the inputs (netlist names, e.g. vV2)
--out  node names to print (the nets the voltmeters probe)

Use it as the oracle before opening Multisim: a state that does not converge here
(status != ok) is a file that Multisim will also fail to solve. The solver is validated
against a GUI reading: Q1_RTL_OR3 gives V(6)=4.610 V; Multisim's meter showed 4.611 V.
"""
import argparse
import itertools
import sys

import dcsolve as D


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--in", dest="ins", nargs="+", required=True)
    ap.add_argument("--out", nargs="+", required=True)
    ap.add_argument("--high", type=float, default=5.0, help="logic-high voltage")
    a = ap.parse_args(argv)

    c, models = D.build(a.path)
    src = {e[1]: k for k, e in enumerate(c.elems) if e[0] == "v"}
    for ref in a.ins:
        if ref not in src:
            sys.exit("no voltage source %r in %s" % (ref, a.path))

    print("%s   inputs=%s   outputs=%s" % (a.path.split("/")[-1], a.ins, a.out))
    print("  " + "  ".join("%-4s" % r for r in a.ins) + " | " + "  ".join("%9s" % o for o in a.out) + " | status")
    for state in itertools.product((0.0, a.high), repeat=len(a.ins)):
        for ref, v in zip(a.ins, state):
            k = src[ref]
            e = c.elems[k]
            c.elems[k] = (e[0], e[1], e[2], v)
        x, _, st = c.solve(models, steps=10, iters=3000)
        d = dict(zip(c.nodes, x)) if st == "ok" else {}
        vals = ["%9.3f" % d[o] if o in d else "%9s" % "-" for o in a.out]
        print("  " + "  ".join("%-4s" % ("%g" % v) for v in state) + " | " + "  ".join(vals) + " | " + st)


if __name__ == "__main__":
    main(sys.argv[1:])
