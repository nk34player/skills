#!/usr/bin/env python3
"""Wire-level connectivity, the way the schematic editor sees it.

    python wiregraph.py ../Q2_TTL_AND2.ms14

netlist.py trusts each net's CiNode port list. The editor instead joins pins by the wire
objects: a wire lists its two end objects (Connect1/Connect2), a pin connector and a
junction list the objects they connect (ConnectList). Two pins are electrically joined only
when a chain of those references links them. This tool builds that graph and reports:

  SPLIT  a logical net whose pins fall into more than one wire island (the editor sees
         separate nets; this is how a ground return or a supply gets lost)
  SHORT  one wire island holding pins of two different logical nets
  ALONE  a pin no wire reaches at all (a floating terminal)

It is the offline mirror of Multisim's ReportNetlist (see multisim_netlist.py).
"""
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

import ms14


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def analyse(path):
    root = ET.fromstring(ms14.unpack(path))
    uf = UF()
    pin_conn = {}          # pin-connector object id -> (component refdes, pin name)
    ports = {}             # CiPort id -> (component refdes, pin name)
    comp_name = {}
    for it in root.iter("Item"):
        if it.get("Class") == "CiComponent" and len(it):
            comp_name[it.get("CiID")] = (it[0].get("LocalName") or "").replace("&ASC", "")
    for it in root.iter("Item"):
        if it.get("Class") == "CiPort" and len(it):
            e = it[0]
            ports[it.get("CiID")] = (comp_name.get(e.get("Component"), "?"),
                                     (e.get("LocalName") or "").replace("&ASC", ""))

    # connection objects live in Objects AND in ReferencedComponents: scan every item
    for it in root.iter("Item"):
        cls, oid = it.get("Class"), it.get("ID")
        el = it[0] if len(it) else None
        if el is None or oid is None:
            continue
        if cls == "CIITLinkComp":
            uf.find(oid)
            for k in ("Connect1", "Connect2"):
                if el.get(k):
                    uf.union(oid, el.get(k))
        elif cls in ("CIITPinConnectorComp", "CODPinComp"):
            uf.find(oid)
            cl = el.find("ConnectList")
            for r in (cl if cl is not None else []):
                if r.get("ID"):
                    uf.union(oid, r.get("ID"))
    # a pin connector belongs to the symbol element (CIITPinSymbolComp) that carries PortID
    for el in root.iter():
        if el.tag == "CIITPinSymbolComp" and el.get("PortID") in ports:
            for it in el.find("Objects") if el.find("Objects") is not None else []:
                if it.get("Class") == "CIITPinConnectorComp":
                    pin_conn[it.get("ID")] = ports[el.get("PortID")]

    # logical nets (CiNode) -> their ports
    dia = next(root.iter("CIITDiagram"))
    logical = {}
    for it in dia.find("Elements"):
        if it.get("Class") != "CiNode":
            continue
        name = (it[0].get("LocalName") or "").replace("&ASC", "")
        logical[name] = [ports.get(r.get("CiID")) for r in it[0].find("Ports")]
    # which pin connector sits on which port
    port_to_conn = {v: k for k, v in pin_conn.items()}

    islands = defaultdict(set)         # island root -> pins (component, pin)
    for pin in pin_conn.values():
        islands[uf.find(port_to_conn[pin])].add(pin)
    pin_island = {}
    for pin, cid in port_to_conn.items():
        pin_island[pin] = uf.find(cid)

    issues = []
    for net, plist in sorted(logical.items()):
        plist = [p for p in plist if p in pin_island]
        roots = defaultdict(list)
        for p in plist:
            roots[pin_island[p]].append(p)
        if len(roots) > 1:
            issues.append(("SPLIT", net, [sorted(v) for v in roots.values()]))
    for root_id, pins in islands.items():
        nets = {n for n, pl in logical.items() for p in pl if p in pins}
        if len(nets) > 1:
            issues.append(("SHORT", sorted(nets), sorted(pins)))
    for net, plist in sorted(logical.items()):
        for p in plist:
            if p in pin_island and sum(1 for q in islands[pin_island[p]]) == 1:
                issues.append(("ALONE", net, p))
    return issues, logical, islands, pin_island


def main(argv):
    path = argv[0]
    issues, logical, islands, pin_island = analyse(path)
    print("%s  logical nets=%d  wire islands=%d" % (path.split("/")[-1], len(logical), len(islands)))
    if not issues:
        print("  CONNECTED: every logical net is one wire island, no shorts, no floating pins")
        return 0
    for kind, *rest in issues:
        if kind == "SPLIT":
            print("  SPLIT net %s -> %d islands: %s" % (rest[0], len(rest[1]), rest[1]))
        elif kind == "SHORT":
            print("  SHORT nets %s share island %s" % (rest[0], rest[1]))
        else:
            print("  ALONE  net %s pin %s" % (rest[0], rest[1]))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
