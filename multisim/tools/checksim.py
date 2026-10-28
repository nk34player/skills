#!/usr/bin/env python3
"""Does this sheet actually simulate, or does it only draw?

    python checksim.py ../Q*.ms14

Every check here is something Multisim tolerates on *open* (the picture looks perfect)
but silently drops when it builds the netlist, which leaves every instrument reading 0 V:

  C1  exactly one CiCircuit, and every CiComponent/@Circuit, CiNode/@Circuit and
      CiModel/@Scope points at it - a part in a circuit that does not exist is not
      simulated at all
  C2  every CiComponent/@Model resolves to a CiModel, and that model is in
      CiCircuit/Models
  C3  no two CiModels share a LocalName (the netlist's subckt name would be ambiguous,
      so a voltmeter can resolve to an ammeter card and read 0 V)
  C4  every card declares the name its CiModel carries, and no two cards declare the
      same one. A card's declared name is what the element line calls, so a mismatch
      expands the device under a name nothing references; two cards declaring one name
      (e.g. every 2N3904 saying ".MODEL Q2N3904/ON") leaves the extra copies' internal
      nodes floating - "Singular matrix. Check node N. Ensure it is not floating with
      respect to net 0", and the analysis is cancelled.
  C5  every instrument's properties block is keyed by its component name (an unbound
      block means no measurement mode and no probed node)
  C6  every pin has a wire referencing its ConnectList id, and every net has >= 2 such
      pins - connectivity is resolved from wire Connect ids, not from the CiNode table
  C7  no id is referenced that exists nowhere (Model / SymCompID / Node / NodeText /
      Connect1 / Connect2 / Circuit / Scope) - a dangling reference is how a wire or an
      instrument ends up attached to nothing
  C8  CiCircuit/Components, /Models and /Nodes list exactly the live objects of that
      class (donor files never file a model under Components)
"""
import collections
import re
import sys
import xml.etree.ElementTree as ET

import ms14


def load(path):
    return ET.fromstring(ms14.unpack(path)) if path.endswith(".ms14") else ET.parse(path).getroot()


def name_of(el):
    return (el.get("LocalName") or "").replace("&ASC", "")


# Parameters that make a solver build a terminal a three-pin device does not have:
#   CJS/VJS/MJS  collector-substrate junction -> a substrate node with no DC path
#   RBM/IRB      second base-resistance split -> an extra internal base node
BJT_EXTRA_TERMINALS = ("CJS", "VJS", "MJS", "RBM", "IRB")
_BJT = re.compile(r"(?i)\.model\s+\S+\s+(?:npn|pnp)\b")


def substrate_nodes(models, els):
    """Referenced BJT cards that declare a parameter needing a fourth terminal.

    The database hands out MODPEX cards carrying CJS/VJS/MJS (and RBM/IRB). On a three-pin
    transistor the substrate node then has only a capacitance to ground, so at DC it is
    genuinely floating: "Singular matrix. Check node N", where N lies past the last
    schematic net because it is a device-internal node, not a wire. Measured on this
    project: nine nets means nodes 0..8, and the solver reported node 14.

    Calibrated against every genuine deck on this machine: the two that contain such a card
    never reference it, so this reports nothing on them.
    """
    out = []
    ref_ids = {it[0].get("Model") for it in els if it.get("Class") == "CiComponent"}
    for mid, mitem in models.items():
        if mid not in ref_ids:
            continue
        el = mitem[0]
        text = " ".join([el.get("LocalName") or ""] +
                        [(cs.get("String") or "") for cs in el.iter("CiaCString")])
        text = text.replace("&ASC", "")
        if not _BJT.search(text):
            continue
        for param in BJT_EXTRA_TERMINALS:
            if re.search(r"(?i)\b" + param + r"\s*=", text):
                out.append("C14 referenced BJT model %r declares %s - it asks for a "
                           "terminal a 3-pin device does not have, which leaves an "
                           "internal node with no DC path (singular matrix)" %
                           (name_of(el), param))
    return out


def check(path):
    root = load(path)
    els = next(root.iter("CIITDiagram")).find("Elements")
    bad = []

    # C1 circuit membership
    circuits = {it.get("CiID") for it in els if it.get("Class") == "CiCircuit"}
    if len(circuits) != 1:
        bad.append("C1 %d CiCircuit objects" % len(circuits))
    for it in els:
        if it.get("Class") in ("CiComponent", "CiNode") and it[0].get("Circuit") not in circuits:
            bad.append("C1 %s %r -> circuit %r" % (it.get("Class"), name_of(it[0]),
                                                   it[0].get("Circuit")))
        if it.get("Class") == "CiModel" and it[0].get("Scope") not in circuits:
            bad.append("C1 model %r -> scope %r" % (name_of(it[0]), it[0].get("Scope")))

    # C2 model references
    models = {it.get("CiID"): it for it in els if it.get("Class") == "CiModel"}
    listed = {r.get("CiID") for r in next(root.iter("CiCircuit")).find("Models")}
    for it in els:
        if it.get("Class") != "CiComponent":
            continue
        mid = it[0].get("Model")
        if mid and mid not in models:
            bad.append("C2 %r model %r missing" % (name_of(it[0]), mid))
        elif mid and mid not in listed:
            bad.append("C2 %r model %r not in CiCircuit/Models" % (name_of(it[0]), mid))

    # C3 unique model names
    seen = collections.Counter(name_of(m[0]) for m in models.values())
    for n, c in seen.items():
        if c > 1:
            bad.append("C3 %d models named %r" % (c, n))

    # C4 card name matches, and is unique across the sheet
    declared = collections.Counter()
    for m in models.values():
        card = ""
        for it in m.iter("CiaCString"):
            card = (it.get("String") or "").replace("&ASC", "")
            break
        toks = card.split()
        for i, tok in enumerate(toks):
            if tok.lower() in (".model", ".subckt") and i + 1 < len(toks):
                declared[toks[i + 1]] += 1
                if toks[i + 1] != name_of(m[0]):
                    bad.append("C4 model %r declares %r"
                               % (name_of(m[0]), toks[i + 1]))
                break
        else:
            bad.append("C4 model %r has no .model/.subckt line" % name_of(m[0]))
    for dup, n in declared.items():
        if n > 1:
            bad.append("C4 %d models declare %r (duplicate model -> floating nodes)"
                       % (n, dup))

    # C10 a model card must be one statement starting at ".MODEL"/".subckt". The
    # database ships MODPEX blocks that open with "*...*" comment lines; stored verbatim
    # the card reads as all-comment, the device gets no model at all and its internal
    # nodes float ("Singular matrix. Check node N").
    for m in models.values():
        for it in m.iter("CiaCString"):
            card = (it.get("String") or "").replace("&ASC", "").strip()
            if not card:
                continue
            head = card.splitlines()[0].strip() if card.splitlines() else ""
            if not re.match(r"(?i)^\.(model|subckt)\s", head):
                bad.append("C10 model %r card starts with %r, not .MODEL/.subckt"
                           % (name_of(m[0]), head[:40]))
            if re.search(r"(?im)^\s*\+", card):
                bad.append("C10 model %r card has '+'-continuation lines (needs one line)"
                           % name_of(m[0]))

    # C11 a component's *database row* must not re-declare a name a CiModel already
    # defines. Every part carries a snapshot of the database row it was placed from in
    # Attributes[4]/strings[5], including that row's own model card. Replacing the model
    # while writing the CiModel's renamed card into that row gives the file two
    # definitions of one name; Multisim builds a model per definition, and the extra
    # copy's internal device nodes belong to no element - a singular matrix at one of
    # them ("Check node 14") on a schematic whose connectivity is perfect.
    # Several parts sharing one database row name is normal and must stay allowed: a
    # schematic with twelve 2N3904s carries twelve identical rows.
    row_names = {}
    for it in els:
        if it.get("Class") != "CiComponent":
            continue
        comp = it[0]
        at = comp.find("Attributes")
        if at is None or len(at) < 5:
            continue
        coll = at[4].find("CiaCollString")
        if coll is None:
            continue
        row = [i.get("Value") or "" for i in coll.iter("Item")]
        if len(row) < 6:
            continue
        txt = row[5].replace("&ASC", "").strip()
        for m in re.finditer(r"(?i)\.(?:model|subckt)\s+(\S+)", txt):
            row_names.setdefault(m.group(1), []).append(
                (comp.get("LocalName") or "").replace("&ASC", ""))
    for name, who in row_names.items():
        for m in models.values():
            for it in m.iter("CiaCString"):
                head = (it.get("String") or "").replace("&ASC", "").strip()
                mm = re.match(r"(?i)^\.(?:model|subckt)\s+(\S+)", head)
                if mm and mm.group(1) == name:
                    bad.append("C11 database row of %s declares %r, which the CiModel "
                               "already defines - duplicated model definition"
                               % (", ".join(sorted(set(who))), name))

    bad.extend(substrate_nodes(models, els))

    # C12 a net label must not take the reference node away.
    # Multisim names a net from its `CSchDesignNetLabel` objects (Project/.../CDesignNetContainer
    # /NetLabels), not from the CiNode. A template that ships labels named "VCC"/"GND" leaves
    # them behind, so the ground net stops being called "0". The netlist check then warns
    #     Warning: No ground node was found in your circuit.
    # and the solver has no reference: every node floats and it reports
    #     Warning: Singular matrix. Check node N.
    # N is just the first floating node it meets, so it moves between runs and between
    # schematics (node 3 for a two-net file, node 14 for a nine-net one) and looks like a
    # connectivity bug in a different place each time.
    # Only the conflict is checked, not the ground net's *name*: real decks name it "GND"
    # (Error.ms14) as often as "0", so requiring a net called "0" would reject them.
    node_names = {(it[0].get("LocalName") or "").replace("&ASC", "")
                  for it in els if it.get("Class") == "CiNode"}
    for lab in root.iter("CSchDesignNetLabel"):
        name = (lab.get("LastNetName") or "").replace("&ASC", "")
        if name.upper() == "GND" and "GND" not in node_names:
            bad.append("C12 net label 'GND' names no net on this sheet - it renames the "
                       "ground net away from '0'")

    # C5 instrument binding
    cnames = {it[0].get("LocalName") for it in els if it.get("Class") == "CiComponent"}
    for node in root.iter("CSourceSymbolCollectNode"):
        key = node.get("CompLongName") or ""
        if key.split("#")[0] not in cnames:
            bad.append("C5 unbound instrument %r" % key)

    # C6 wire-level connectivity
    pin_conn = {}
    for objs in root.iter("Objects"):
        for it in objs:
            if it.get("Class") != "CIITPinSymbolComp":
                continue
            for conn in it.iter("CIITPinConnectorComp"):
                cl = conn.find("ConnectList")
                for ref in (cl if cl is not None else []):
                    pin_conn[ref.get("ID")] = name_of(conn)
    wired = collections.Counter()
    for objs in root.iter("Objects"):
        for it in objs:
            if it.get("Class") != "CIITLinkComp":
                continue
            for attr in ("Connect1", "Connect2"):
                if it[0].get(attr) in pin_conn:
                    wired[it[0].get(attr)] += 1
    loose = [cid for cid in pin_conn if wired[cid] == 0]
    if loose:
        bad.append("C6 %d pin(s) with no wire: %s" % (len(loose), loose[:6]))

    # C7 dangling references
    ids = {it.get("CiID") for it in els if it.get("CiID")}
    ids |= {o.get("ID") for objs in root.iter("Objects") for o in objs if o.get("ID")}
    ids |= {o.get("ID") for rc in root.iter("ReferencedComponents")
            for o in rc if o.get("ID")}
    dangling = collections.Counter()
    for el in root.iter():
        for k, v in el.attrib.items():
            if k in ("CiID", "Model", "SymCompID", "Node", "NodeText", "Circuit", "Scope",
                     "Connect1", "Connect2") or k.endswith("CiID"):
                # "0" is a real setting on ERC_CHK_OPTIONS, not an id
                if v and v.isdigit() and v not in ids and v != "0":
                    dangling[k] += 1
    if dangling:
        bad.append("C7 dangling refs %s" % dict(dangling))

    # C8 circuit list membership
    circ = next(root.iter("CiCircuit"))
    cls_of = {it.get("CiID"): it.get("Class") for it in els if it.get("CiID")}
    for tag, want in (("Components", "CiComponent"), ("Models", "CiModel"),
                      ("Nodes", "CiNode")):
        lst = circ.find(tag)
        if lst is None:
            continue
        got = collections.Counter(cls_of.get(r.get("CiID"), "MISSING") for r in lst)
        if got and set(got) != {want}:        # an empty list is legitimate (no models)
            bad.append("C8 %s holds %s, expected only %s" % (tag, dict(got), want))

    return bad


def main(paths):
    bad_total = 0
    for path in paths:
        bad = check(path)
        bad_total += len(bad)
        print("%-22s %s" % (path.rsplit("/", 1)[-1],
                            "SIMULATABLE" if not bad else "WILL NOT SIMULATE"))
        for b in bad[:12]:
            print("    " + b)
    return 1 if bad_total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
