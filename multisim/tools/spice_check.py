#!/usr/bin/env python3
"""Independent check: run the sheet's netlist in ngspice (.op) for each input state.

    python spice_check.py ../Q2_TTL_AND2.ms14 --in vV2 vV3 --out X Y

Same netlist as netlist.py, same .model cards as dcsolve.py. Each voltmeter becomes its
1 GOhm R_multi_meter to ground. Needs ngspice (scoop install ngspice).
"""
import argparse
import itertools
import os
import re
import subprocess
import sys
import tempfile

import dcsolve
import netlist

NGSPICE = os.environ.get("NGSPICE", r"C:\Users\PC\scoop\apps\ngspice\current\bin\ngspice_con.exe")


def model_lines(path):
    """.MODEL cards, one line each, in SPICE syntax (no '+' tokens, no NPN(...) brackets)."""
    out = []
    for _ref, card in dcsolve.cards(path).items():
        if re.match(r"(?i)\s*\.subckt", card):        # instrument subckt: not needed here
            continue
        c = " ".join(card.replace("\r", " ").replace("\n", " ").split())
        c = re.sub(r"\s\+(?=\s)", " ", c)              # lone '+' continuation tokens
        c = re.sub(r"(?i)\b(npn|pnp)\((.*)\)", r"\1 \2", c)
        out.append(c)
    return out


def deck(path, sets, outs):
    lines, _ = netlist.build(path)
    body = []
    for ln in lines:
        t = ln.split()
        if not t:
            continue
        if t[0][0].lower() == "x":                    # instrument subckt -> 1 GOhm to ground
            body.append("RM_%s %s 0 1e9" % (t[0], t[1]))
            continue
        if t[0][0].lower() == "v" and t[0] in sets:   # input state
            t = [t[0], t[1], t[2], "dc", "%g" % sets[t[0]]]
        body.append(" ".join(t))
    ctrl = [".control", "op"] + ["print v(%s)" % o for o in outs] + ["quit", ".endc"]
    return "\n".join(["* sheet check"] + body + model_lines(path) + ctrl + [".end", ""])


def run(text):
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as f:
        f.write(text)
        name = f.name
    try:
        p = subprocess.run([NGSPICE, "-b", name], capture_output=True, text=True, timeout=120)
        return p.stdout + p.stderr
    finally:
        os.unlink(name)


def values(out, outs):
    res = {}
    for o in outs:
        m = re.search(r"v\(%s\)\s*=\s*([-+0-9.eE]+)" % re.escape(o), out, re.I)
        res[o] = float(m.group(1)) if m else float("nan")
    return res


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--in", dest="ins", nargs="+", required=True)
    ap.add_argument("--out", nargs="+", required=True)
    ap.add_argument("--high", type=float, default=5.0)
    ap.add_argument("--dump", action="store_true", help="print the deck and the ngspice log")
    a = ap.parse_args(argv)
    print("%s  ngspice .op  inputs=%s" % (a.path.split("/")[-1], a.ins))
    for state in itertools.product((0.0, a.high), repeat=len(a.ins)):
        text = deck(a.path, dict(zip(a.ins, state)), a.out)
        out = run(text)
        if a.dump:
            print(text)
            print(out)
        v = values(out, a.out)
        print("  " + " ".join("%s=%g" % (i, s) for i, s in zip(a.ins, state)) + "   " +
              "  ".join("%s=%9.4f" % (o, v[o]) for o in a.out))


if __name__ == "__main__":
    main(sys.argv[1:])
