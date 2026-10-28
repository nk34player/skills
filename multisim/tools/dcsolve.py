#!/usr/bin/env python3
"""Solve the DC operating point of a generated sheet, without Multisim.

    python dcsolve.py ../Q1_RTL_OR3.ms14          # operating point + meter readings
    python dcsolve.py ../Q1_RTL_OR3.ms14 -v       # also print the matrix condition

Multisim's "Singular matrix. Check node N. Ensure it is not floating with respect to net
0" is a linear-algebra statement: the MNA matrix has no unique solution. This builds the
same matrix from the expanded netlist and reports it, so a defect is found offline instead
of by opening the GUI:

  * nodes with no conducting path to 0 make the matrix singular - listed by name, which is
    what the dialog's node number is only guessing at
  * the condition number says how close to singular a solvable circuit sits
  * the solution is the operating point, i.e. what the voltmeters should show

Devices: R, V(dc), I(dc), Q (Gummel-Poon subset), M (level 1), D. Anything else is
reported, never silently dropped.
"""
import math
import re
import sys

import numpy as np

import netlist

TEMPC = 27.0
VT = 8.617333262e-5 * (TEMPC + 273.15)

# SPICE's GMIN: a 1e-12 S conductance from every node to ground. It is what keeps a node
# that is only behind an off transistor solvable instead of "singular matrix", and every
# real simulator (Multisim included) applies it.
GMIN = 1e-12
_GMIN = [GMIN]   # current value, so gmin stepping can drive it


# ----------------------------------------------------------------- netlist ----
def cards(path):
    """refdes -> the model card text its element line resolves to."""
    root = netlist.load(path)
    els = next(root.iter("CIITDiagram")).find("Elements")
    models = {it.get("CiID"): it for it in els if it.get("Class") == "CiModel"}
    out = {}
    for it in els:
        if it.get("Class") != "CiComponent":
            continue
        c = it[0]
        m = models.get(c.get("Model"))
        if m is None:
            continue
        for s in m.iter("CiaCString"):
            out[(c.get("LocalName") or "").replace("&ASC", "")] = (
                (s.get("String") or "").replace("&ASC", ""))
            break
    return out


def params(card):
    """'.MODEL name TYPE K=V ...' or 'NPN(K=V ...)' -> (TYPE, {K: float}).

    The type is the word right after the model name. Flattened cards glue it to the
    parenthesis ("NPN(Is=6.7f"), so match letters only. Values carry SPICE scale suffixes
    (6.734f, 66.78m, 1meg) that float() rejects - they go through _val().
    """
    txt = (card or "").replace("\r\n", "\n")
    txt = " ".join(l for l in txt.split("\n") if not l.strip().startswith("*"))
    kind = ""
    m = re.search(r"(?i)\.(?:model|subckt)\s+\S+\s+([A-Za-z]+)", txt)
    if m:
        kind = m.group(1).upper()
    vals = {}
    for m in re.finditer(r"([A-Za-z][A-Za-z0-9_]*)\s*=\s*([-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?[A-Za-z]*)", txt):
        try:
            vals[m.group(1).upper()] = _val(m.group(2))
        except ValueError:
            pass
    return kind, vals


def _val(tok):
    m = re.match(r"([-+0-9.eE]+)\s*([a-zA-Z]*)", tok)
    if not m:
        raise ValueError(tok)
    # SPICE scale suffixes are case-insensitive: M and m are both milli, F is femto
    suffix = m.group(2).lower()
    scale = {"f": 1e-15, "a": 1e-18, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3,
             "k": 1e3, "g": 1e9, "t": 1e12}
    if suffix.startswith("meg"):
        mult = 1e6
    elif suffix and suffix[0] in scale:
        mult = scale[suffix[0]]
    else:
        mult = 1.0
    return float(m.group(1)) * mult


# ----------------------------------------------------------------- devices ----
class BJT:
    """Gummel-Poon DC core: transport current, beta, Early voltage, high-level roll-off."""

    def __init__(self, p):
        self.IS = p.get("IS", 1e-14)
        self.BF = p.get("BF", 100.0)
        self.BR = p.get("BR", 1.0)
        self.NF = p.get("NF", 1.0)
        self.NR = p.get("NR", 1.0)
        self.VAF = p.get("VAF", 0.0)
        self.IKF = p.get("IKF", 0.0)
        self.ISE = p.get("ISE", 0.0)
        self.NE = p.get("NE", 1.5)
        self.ISC = p.get("ISC", 0.0)
        self.NC = p.get("NC", 2.0)
        self.IKR = p.get("IKR", 0.0)
        self.RB = p.get("RB", 0.0)
        self.RE = p.get("RE", 0.0)
        self.RC = p.get("RC", 0.0)

    def currents(self, vbe, vbc):
        nfvt, nrvt = self.NF * VT, self.NR * VT
        ef = math.exp(min(vbe / nfvt, 60))
        er = math.exp(min(vbc / nrvt, 60))
        iff = self.IS * (ef - 1)
        irr = self.IS * (er - 1)
        if self.IKF:
            iff /= 1.0 + iff / self.IKF
        if self.IKR:
            irr /= 1.0 + irr / self.IKR
        qb = 1.0 / (1.0 - vbc / self.VAF) if self.VAF else 1.0
        qb = max(qb, 1e-3)
        ic = iff / qb - irr
        ib = iff / self.BF + irr / self.BR
        if self.ISE:
            ib += self.ISE * (math.exp(min(vbe / (self.NE * VT), 60)) - 1)
        if self.ISC:
            ib += self.ISC * (math.exp(min(vbc / (self.NC * VT), 60)) - 1)
        return ic, ib

    def jac(self, vbe, vbc):
        h = 1e-7
        ic0, ib0 = self.currents(vbe, vbc)
        ic1, ib1 = self.currents(vbe + h, vbc)
        ic2, ib2 = self.currents(vbe, vbc + h)
        return (ic0, ib0,
                (ic1 - ic0) / h, (ic2 - ic0) / h,
                (ib1 - ib0) / h, (ib2 - ib0) / h)


class MOS:
    """Level-1 switch, bulk tied to source. A PMOS is the NMOS mirrored through zero.

    Mirroring matters for more than sign: writing the PMOS equations out directly gives a
    *negative* drain conductance at vds=0, and a negative conductance makes the node it
    feeds look like it has no path at all - a singular matrix that the circuit does not
    actually have.
    """

    def __init__(self, p):
        self.VT0 = p.get("VT0", 2.0)
        self.KP = p.get("KP", 1e-4)
        self.LAMBDA = p.get("LAMBDA", 0.0)
        self.pmos = self.VT0 < 0

    def currents(self, vgs, vds):
        """Drain current, positive flowing d -> s."""
        if self.pmos:
            vgs, vds = -vgs, -vds
        vt = abs(self.VT0)
        vov = vgs - vt
        if vov <= 0:
            return 0.0
        if vds < vov:                       # triode
            i = self.KP * (vov * vds - 0.5 * vds * vds)
        else:                               # saturation
            i = 0.5 * self.KP * vov * vov
        i *= (1.0 + self.LAMBDA * abs(vds))
        return -i if self.pmos else i

    def jac(self, vgs, vds):
        h = 1e-7
        i0 = self.currents(vgs, vds)
        i1 = self.currents(vgs + h, vds)
        i2 = self.currents(vgs, vds + h)
        return i0, (i1 - i0) / h, (i2 - i0) / h


# ----------------------------------------------------------------- circuit ----
class Circuit:
    def __init__(self):
        self.nodes = ["0"]
        self.idx = {"0": 0}
        self.elems = []
        self.instruments = []
        self.unknown = []

    def node(self, name):
        if name not in self.idx:
            self.idx[name] = len(self.nodes)
            self.nodes.append(name)
        return self.idx[name]

    def add(self, line):
        toks = line.split()
        if not toks:
            return
        ref, kind = toks[0], toks[0][0].lower()
        try:
            if kind == "r":
                self.elems.append(("r", ref, (self.node(toks[1]), self.node(toks[2])),
                                   _val(toks[3])))
            elif kind in ("v", "i"):
                dc = 0.0
                for i, t in enumerate(toks):
                    if t.lower() == "dc" and i + 1 < len(toks):
                        dc = _val(toks[i + 1])
                self.elems.append((kind, ref, (self.node(toks[1]), self.node(toks[2])), dc))
            elif kind == "q":
                self.elems.append(("q", ref, (self.node(toks[1]), self.node(toks[2]),
                                              self.node(toks[3])),
                                   toks[4] if len(toks) > 4 else ""))
            elif kind == "m":
                self.elems.append(("m", ref, (self.node(toks[1]), self.node(toks[2]),
                                              self.node(toks[3])),
                                   toks[5] if len(toks) > 5 else ""))
            elif kind == "d":
                self.elems.append(("d", ref, (self.node(toks[1]), self.node(toks[2])),
                                   toks[3] if len(toks) > 3 else ""))
            elif kind == "x":
                self.instruments.append((ref, self.node(toks[1]), self.node(toks[2])))
            else:
                self.unknown.append(line)
        except (IndexError, ValueError):
            self.unknown.append(line)

    # linear part: R, I and the extra rows for V sources
    def linear(self):
        n = len(self.nodes)
        vsrc = [e for e in self.elems if e[0] == "v"]
        size = n + len(vsrc)
        A = np.zeros((size, size))
        b = np.zeros(size)
        row_of = {}
        for k, (_, ref, (a, c), val) in enumerate(vsrc):
            row_of[ref] = n + k
            A[a, n + k] += 1.0
            A[c, n + k] -= 1.0
            A[n + k, a] += 1.0
            A[n + k, c] -= 1.0
            b[n + k] = val
        for i in range(1, n):
            A[i, i] += _GMIN[0]             # shunt to ground, as SPICE does
        for kind, ref, nd, data in self.elems:
            if kind == "r":
                g = 1.0 / max(data, 1e-12)
                a, c = nd
                A[a, a] += g
                A[c, c] += g
                A[a, c] -= g
                A[c, a] -= g
            elif kind == "i":
                a, c = nd
                b[a] -= data
                b[c] += data
        return A, b

    def residual(self, v, models):
        """KCL residual of the nonlinear devices: current *leaving* each node.

        Writing the device currents explicitly (instead of stamping conductances by hand)
        keeps the physics in one place, and the Jacobian is then taken numerically, so
        there is no sign or column-order bookkeeping to get wrong.
        """
        n = len(self.nodes)
        f = np.zeros(n)
        for kind, ref, nd, _data in self.elems:
            m = models.get(ref) or models.get(ref[1:])
            if m is None:
                continue
            if kind == "q":
                c, b_, e = nd
                ic, ib = m.currents(v[b_] - v[e], v[b_] - v[c])
                f[c] += ic
                f[b_] += ib
                f[e] -= ic + ib
            elif kind == "m":
                d, g, s = nd
                i0 = m.currents(v[g] - v[s], v[d] - v[s])
                f[d] += i0
                f[s] -= i0
            elif kind == "d":
                a, k = nd
                i0m, nn = m[0], m[1]
                vt = nn * VT
                cur = i0m * (math.exp(min((v[a] - v[k]) / vt, 60)) - 1.0)
                f[a] += cur
                f[k] -= cur
        return f

    def devices(self, x, models):
        """(G, R) such that the next linear system is  (A + G) v = b - R."""
        n = len(self.nodes)
        f0 = self.residual(x, models)
        G = np.zeros((n, n))
        h = 1e-6
        for k in range(1, n):                    # node 0 is fixed at 0 V
            vp = x.copy()
            vp[k] += h
            G[:, k] = (self.residual(vp, models) - f0) / h
        return G, f0 - G.dot(x[:n])

    @staticmethod
    def _reduce(M, v):
        """Drop the ground node's row and column.

        Node 0 is fixed at 0 V, so its KCL row is implied by the others; keeping it makes
        the matrix rank-deficient for *any* circuit (a uniform null vector), which is not
        a property of the schematic.
        """
        keep = [i for i in range(len(v)) if i != 0]
        return M[np.ix_(keep, keep)], v[keep], keep

    def newton(self, models, x, iters=300):
        """Damped Newton at the current source values: (x, matrix, status)."""
        n = len(self.nodes)
        last = None
        for _ in range(iters):
            A, b = self.linear()
            G, R = self.devices(x, models)
            M = A.copy()
            M[:n, :n] += G
            bb = b.copy()
            bb[:n] -= R
            Mr, br, keep = self._reduce(M, bb)
            try:
                sol = np.linalg.solve(Mr, br)
            except np.linalg.LinAlgError:
                return x, Mr, "singular"
            new = np.zeros(len(bb))
            for k, i in enumerate(keep):
                new[i] = sol[k]
            delta = new[:n] - x[:n]
            delta[0] = 0.0                     # ground is fixed by definition
            size = np.max(np.abs(delta)) if n else 0.0
            last = size
            # Junction limiting: a full Newton step off the exponential is enormous, so
            # take a fraction of it while the step is still large.
            scale = min(1.0, 0.5 / size) if size > 0.5 else 1.0
            x = x + np.concatenate([delta * scale,
                                    np.zeros(len(x) - n)]) if len(x) > n else x + delta * scale
            if size < 1e-9:
                return x, Mr, "ok"
        return x, M, ("no convergence (last step %.3e)" % last if last else "no convergence")

    def solve(self, models, steps=4, iters=300):
        """Solve with SPICE's two fallbacks: gmin stepping, then source stepping."""
        n = len(self.nodes)
        srcs = [k for k, e in enumerate(self.elems) if e[0] == "v"]
        vmax = max([abs(self.elems[k][3]) for k in srcs] + [0.0])

        def seed():
            x = np.zeros(len(self.linear()[1]))
            x[:n] = vmax
            x[0] = 0.0
            for k in srcs:                       # supplies at their real value
                _, _, (a, c), val = self.elems[k]
                if a:
                    x[a] = val
                if c:
                    x[c] = val
            return x

        # 1. straight Newton from the seeded point
        x, M, status = self.newton(models, seed(), iters=iters)
        if status == "ok":
            return x, M, status

        # 2. gmin stepping: solve with a large shunt conductance, then shrink it
        saved = _GMIN[0]
        x = seed()
        try:
            for g in (1e-3, 1e-4, 1e-5, 1e-6, 1e-7, 1e-8, 1e-9, 1e-10, 1e-11, GMIN):
                _GMIN[0] = g
                x, M, status = self.newton(models, x, iters=iters)
                if status != "ok":
                    break
        finally:
            _GMIN[0] = saved
        if status == "ok":
            return x, M, status

        # 3. source stepping, smallest useful number of ramps
        values = {k: self.elems[k][3] for k in srcs}
        x = seed()
        for frac in [i / float(steps) for i in range(1, steps + 1)] + [1.0]:
            for k in srcs:
                self.elems[k] = ("v", self.elems[k][1], self.elems[k][2], values[k] * frac)
            x, M, status = self.newton(models, x, iters=iters)
            if status == "singular":
                break
        for k in srcs:
            self.elems[k] = ("v", self.elems[k][1], self.elems[k][2], values[k])
        return x, M, status

    def floating_nodes(self, models):
        """Nodes with no conducting path at all - the usual singular-matrix cause."""
        has = {}
        for kind, ref, nd, data in self.elems:
            if kind == "x":
                continue
            for a in nd[:2] if len(nd) >= 2 else nd:
                has.setdefault(a, set()).add(kind)
        lone = []
        for i, nm in enumerate(self.nodes):
            if i == 0:
                continue
            kinds = has.get(i, set())
            if not kinds:
                lone.append(nm)
        return lone


# -------------------------------------------------------------------- main ----
def build(path):
    lines, _ = netlist.build(path)
    c = Circuit()
    for ln in lines:
        c.add(ln)
    models = {}
    for ref, card in cards(path).items():
        kind, p = params(card)
        if kind == "NPN" or kind == "PNP":
            models[ref] = BJT(p)
        elif kind in ("NMOS", "PMOS"):
            models[ref] = MOS(p)
        elif kind in ("D", "DIODE"):
            models[ref] = (p.get("IS", 1e-14), p.get("N", 1.0), p.get("RS", 0.0))
    return c, models


def main(argv):
    paths = [a for a in argv if not a.startswith("-")]
    verbose = "-v" in argv
    rc = 0
    for path in paths:
        c, models = build(path)
        x, M, status = c.solve(models)
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        extra = ""
        if c.unknown:
            extra = "  (unsupported: %s)" % "; ".join(u.split()[0] for u in c.unknown)
        verdict = {"ok": "SOLVED", "singular": "SINGULAR (defect in the file)"}.get(
            status, "NO CONVERGENCE (solver limit, not a file defect)")
        print("%-22s nodes=%-3d devices=%-3d %s%s"
              % (name, len(c.nodes), len(c.elems), verdict, extra))
        if status == "singular":
            lone = c.floating_nodes(models)
            if lone:
                print("   NO CONDUCTING PATH TO 0: %s" % ", ".join(lone))
            rc = 1
            continue
        if status != "ok":
            rc = 1
            continue
        if verbose:
            try:
                print("   condition number %.3e" % np.linalg.cond(M))
            except Exception:
                pass
            print("   meters connect but do not conduct (see nodes below)")
        for ref, a, b in c.instruments:
            print("   %-6s V(%s) - V(%s) = %+.4f V"
                  % (ref, c.nodes[a], c.nodes[b], x[a] - x[b]))
        if verbose:
            for i, nm in enumerate(c.nodes):
                if i:
                    print("     V(%-6s) = %+.4f V" % (nm, x[i]))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
