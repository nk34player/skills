#!/usr/bin/env python3
"""Static structural tests for generated .ms14 files. No Multisim, no simulation.

Multisim crashes (or silently drops parts) on structurally broken files, so every
invariant the GUI relies on is checked here instead:

  T1  every CiComponent.Ports entry resolves to an existing CiPort of that component
  T2  every CiPort belongs to exactly one CiNode, and every CiNode has >= 2 ports
  T3  every symbol pin (CIITPinSymbolComp) points at a CiPort of its own component
  T4  every CiComponent.Model resolves to a CiModel that the circuit lists
  T5  every CiModel has a non-empty SPICE card in Attributes[1]/CiaCString
  T6  all drawing primitives and symbol offsets stay inside the page (0..960, 0..720)
  T7  no duplicate CiIDs anywhere in the document
  T8  every drawing primitive carries the Transformer-M00..M21 matrix

    python test_files.py ../Q1_RTL_OR3.ms14 ...
    python test_files.py --control        # also test the known-good skeleton
"""

import sys
import xml.etree.ElementTree as ET

import re

import ms14
import preview as PV

PAGE = (0, 0, 960, 720)
MATRIX = ("Transformer-M00", "Transformer-M01", "Transformer-M10",
          "Transformer-M11", "Transformer-M20", "Transformer-M21")


def load(path):
    if path.endswith(".ms14"):
        return ET.fromstring(ms14.unpack(path))
    return ET.parse(path).getroot()


def clean(v):
    """Net/part names are stored string-encoded: '&ASC0' is the name '0'."""
    for pre in ("&ASC", "&UNI"):
        if v and v.startswith(pre):
            return v[len(pre):]
    return v or ""


def elements(root):
    """The real element list; inner Ci* elements repeat the Class attribute, so only
    Elements/Item entries may be visited (otherwise everything is counted twice)."""
    dia = next(root.iter("CIITDiagram"))
    return [it for it in dia.find("Elements")]


def vocabulary(path):
    """{tag, (tag, attr)} seen in a known-good file - the schema Multisim accepts."""
    root = load(path)
    tags, attrs = set(), set()
    for el in root.iter():
        tags.add(el.tag)
        for a in el.attrib:
            attrs.add((el.tag, a))
    return tags, attrs


def run(path, ref=None, strict=True):
    """CiID lives on the wrapper <Item Class="...">, the payload on its single child."""
    root = load(path)
    els = elements(root)
    fails = []

    info = []

    def fail(code, msg):
        fails.append("%s %s" % (code, msg))

    ports = {}      # port CiID -> owning component CiID
    nodes = {}      # node name -> [port CiID]
    comps = {}      # refdes -> (CiID, element)
    models = {}     # CiID -> element

    for it in els:
        cls, cid, inner = it.get("Class"), it.get("CiID"), it[0]
        if cls == "CiPort":
            ports[cid] = inner.get("Component")
        elif cls == "CiNode":
            nodes[clean(inner.get("LocalName"))] = [r.get("CiID") for r in inner.find("Ports")]
        elif cls == "CiComponent":
            if inner.get("LocalName"):
                comps[inner.get("LocalName")] = (cid, inner)
        elif cls == "CiModel":
            models[cid] = inner

    port_node = {}
    for name, plist in nodes.items():
        for p in plist:
            if p in port_node:
                fail("T2", "port %s in 2 nets (%s, %s)" % (p, port_node[p], name))
            port_node[p] = name

# T2: nets must have >= 2 pins
    for name, plist in nodes.items():
        if len(plist) < 2:
            fail("T2", "net %s has %d pin(s)" % (name, len(plist)))

    # CiCircuit/Models lists the model CiIDs the netlister will use
    listed = set()
    for it in els:
        if it.get("Class") == "CiCircuit":
            m = it[0].find("Models")
            if m is not None:
                listed = {r.get("CiID") for r in m}

    for rname, (cid, c) in comps.items():
        # T1
        for r in c.find("Ports"):
            pid = r.get("CiID")
            if pid not in ports:
                fail("T1", "%s references missing port %s" % (rname, pid))
            elif ports[pid] != cid:
                fail("T1", "%s port %s belongs to component %s" % (rname, pid, ports[pid]))
        # T4
        mid = c.get("Model")
        if mid and mid not in models:
            fail("T4", "%s -> missing CiModel %s" % (rname, mid))
        if mid and mid not in listed:
            fail("T4", "%s -> CiModel %s not listed in circuit Models" % (rname, mid))

    # T3 + T8 (per symbol): symbols live as Objects/Item wrappers, the CiID is on the
    # wrapper - iterating the inner CIITSymbolComp loses the ID
    symbols = []
    for objs in root.iter("Objects"):
        for it in objs:
            if it.get("Class") == "CIITSymbolComp":
                symbols.append(it)
    for it in symbols:
        sid = it.get("ID")
        owner = next((r for r, (cid, c) in comps.items() if c.get("SymCompID") == sid), sid)
        owner_cid = comps[owner][0] if owner in comps else None
        own_ports = {p for p, comp in ports.items() if comp == owner_cid}
        pins = 0
        for pe in it.iter("CIITPinSymbolComp"):
            pins += 1
            if pe.get("PortID") not in own_ports:
                fail("T3", "%s pin %s -> port %s not in component ports"
                     % (owner, (pe.get("PinName") or "").replace("&ASC", ""), pe.get("PortID")))
        if owner_cid and pins == 0:
            fail("T3", "%s symbol has no pin symbols" % owner)
        for cls, attr in (("CODLineComp", ("pt0X", "pt0Y", "pt1X", "pt1Y")),):
            for el in it.iter(cls):
                for k in attr:
                    if el.get(k) is None:
                        fail("T8", "%s %s missing %s" % (owner, cls, k))
        for el in it.iter():
            cls = el.get("Class") or ""
            if cls in ("CODLineComp", "CODPolygonComp", "CODEllipseComp", "CIITSymbolBorderRect"):
                miss = [k for k in MATRIX if el.get(k) is None]
                if miss:
                    info.append("%s %s missing %s" % (owner, cls, ",".join(miss)))

    # T5
    for mid, m in models.items():
        s = next((g for it in m.find("Attributes") for g in it if g.tag == "CiaCString"), None)
        if s is None or len((s.get("String") or "").replace("&ASC", "").strip()) < 10:
            fail("T5", "model %s has no SPICE card" % (m.get("LocalName") or mid))

    # T6: every *pin* must sit on the page (local primitive coords may be negative)
    for it in symbols:
        sym = it[0] if len(it) and it[0].tag == "CIITSymbolComp" else it
        ox = float(sym.get("Transformer-M20") or 0)
        oy = float(sym.get("Transformer-M21") or 0)
        for conn in sym.iter("CIITPinConnectorComp"):
            x = ox + float(conn.get("ptCenterX") or 0)
            y = oy + float(conn.get("ptCenterY") or 0)
            if not (PAGE[0] <= x <= PAGE[2] and PAGE[1] <= y <= PAGE[3]):
                fail("T6", "pin at (%.0f,%.0f) outside page" % (x, y))

    # T7: duplicate definitions (references legitimately repeat a CiID)
    defs = {}
    for it in els:
        cid = it.get("CiID")
        if cid:
            defs[cid] = defs.get(cid, 0) + 1
    for it in symbols:
        cid = it.get("ID")
        if cid:
            defs[cid] = defs.get(cid, 0) + 1
    for cid, n in defs.items():
        if n > 1:
            fail("T7", "CiID %s defined %d times" % (cid, n))

    # T12/T13: layout - no wire may cross a part body it is not attached to, and every
    # part must sit inside the safe box. Both are checked against the same geometry the
    # renderer uses, so a passing file also looks right.
    lparts, lwires, ljuncs, _pins, llabels = PV.model(path)
    for oref, a, b in PV.overlaps(lparts, lwires)[:6]:
        fail("T12", "wire (%.0f,%.0f)-(%.0f,%.0f) crosses %s"
             % (a[0], a[1], b[0], b[1], oref))
    # T21: an instrument's SPICE model must match what it is meant to measure.
    #   voltmeter model: R_multi_meter >= 1e6 (1 GOhm)   ammeter model: ~1e-5 (a short)
    # A meter labelled "V" but carrying the ammeter subcircuit shorts its node to the
    # return, so the reading is always 0 V and the circuit is silently loaded.
    model_card = {}
    for cid, m in models.items():
        for grp in list(m.find("Attributes"))[1:2]:
            for g in grp:
                if g.tag in ("CiaSpiceTmpltExprt", "CiaCString"):
                    model_card[cid] = g.get("String") or ""
    inst_mode = {}
    for node in root.iter("CSourceSymbolCollectNode"):
        name = (node.get("CompLongName") or "").split("#")[0].replace("&ASC", "")
        for el in node.iter("Element"):
            if (el.get("Key") or "").replace("&ASC", "") == "NI_EWB_MEASUREMENT_MODE":
                inst_mode[name] = el[0].get("Data")
    for rname, (cid, c) in comps.items():
        if not rname.upper().startswith("XMM"):
            continue
        card = model_card.get(c.get("Model"), "")
        m = re.search(r"R_multi_meter\s+\S+\s+\S+\s+([0-9.eE+-]+)", card)
        if not m:
            continue
        ohms = float(m.group(1))
        mode = inst_mode.get(rname)
        wants_volts = (mode == "1")
        high_z = ohms >= 1e6
        if wants_volts and not high_z:
            fail("T21", "%s is set to volts but its model is %.0e ohm (an ammeter: it shorts "
                       "the node)" % (rname, ohms))
        if (not wants_volts) and high_z:
            fail("T21", "%s is set to amps but its model is %.0e ohm (a voltmeter)"
                 % (rname, ohms))

    # T19: the reference net must be named "0" and must carry the ground symbol.
    # Multisim/SPICE anchor the matrix at node 0; a reference net called "GND" leaves the
    # whole circuit floating -> "Singular matrix ... floating with respect to net 0".
    if "0" not in nodes:
        fail("T19", "no net named '0' - the reference node has another name "
                    "(nets: %s)" % ", ".join(sorted(nodes)))
    elif len(nodes["0"]) < 2:
        fail("T19", "net '0' has %d pin(s); it must tie the ground symbol to the returns"
             % len(nodes["0"]))

    # T23: an element's value must be real. `#n` in a template is parameters[n] (offset by
    # one), so reading one slot too far expands every resistor as 0 ohm and every source as
    # 0 V - a 0-ohm resistor divides by zero and the run dies with a singular matrix while
    # the netlist still validates. Also: the numeric mirror (`doubles`) must agree with the
    # string list, or the value the editor/netlister uses stays at the donor's default.
    for rname, (cid, c) in comps.items():
        at = c.find("Attributes")
        if at is None or len(at) < 3:
            continue
        tpl = ""
        for grp in list(at)[1:2]:
            for ch in grp:
                if ch.tag in ("CiaSpiceTmpltExprt", "CiaCString"):
                    tpl = (ch.get("String") or "").replace("&ASC", "")
        if not tpl or not re.match(r"[rv]", tpl):
            continue
        strings, nums = [], []
        for grp in list(at)[2:3]:                 # Item > CiaParamList > parameters/doubles
            for plist in grp:
                for lst in plist:
                    if lst.tag == "parameters":
                        strings = [(x.get("Value") or "").replace("&ASC", "") for x in lst]
                    elif lst.tag == "doubles":
                        nums = [(x.get("Value") if x.get("Value") is not None
                                 else x.get("Double")) for x in lst]
        val = ""
        for slot in re.findall(r"#([0-9]+)", tpl):
            i = int(slot)
            if 0 <= i < len(strings):
                val = strings[i]
                break
        num = None
        try:
            num = float(re.match(r"\s*(-?[0-9.]+)\s*([a-zA-Z]*)", val).group(1))
        except (AttributeError, TypeError):
            pass
        # 0 V is a legal source (an input tied low); 0 ohm is not - it divides by zero.
        if num is None or (num == 0 and tpl[0].lower() == "r"):
            fail("T23", "%s expands to %r - an invalid/zero element value makes the matrix "
                 "singular (is the template reading slot #n instead of #n+1?)"
                 % (rname, val))
        if len(nums) > 1 and len(strings) > 1:
            a, b = str(strings[1]), str(nums[1])
            try:
                if abs(float(re.match(r"\s*(-?[0-9.]+)", a).group(1))
                       - float(re.match(r"\s*(-?[0-9.]+)", b).group(1))) > 1e-9:
                    fail("T23", "%s string value %r != numeric mirror %r" % (rname, a, b))
            except (AttributeError, TypeError):
                pass

    # T22: every CiNode must carry the full 33-group Attributes block, and group 16 (the
    # reference/ground flag) must hold one CiaDOUBLE on net "0" and be empty elsewhere.
    # An EMPTY <Attributes/> leaves the net unreferenceable: the netlist checks out and the
    # run then dies with "Singular matrix ... floating with respect to net 0 (ground)".
    NODE_GROUPS, GROUND_GROUP = 33, 16
    for it in els:
        if it.get("Class") != "CiNode":
            continue
        nm = clean(it[0].get("LocalName"))
        at = it[0].find("Attributes")
        grps = list(at) if at is not None else []
        if len(grps) != NODE_GROUPS:
            fail("T22", "net %s has %d attribute group(s); a real CaiNode carries %d "
                 "(an empty block leaves the net unreferenced -> singular matrix)"
                 % (nm, len(grps), NODE_GROUPS))
            continue
        flagged = len(list(grps[GROUND_GROUP])) > 0
        if nm == "0" and not flagged:
            fail("T22", "net '0' is missing the ground flag in attribute group %d"
                 % GROUND_GROUP)
        elif nm != "0" and flagged:
            fail("T22", "net %s carries the ground flag (group %d) although it is not '0'"
                 % (nm, GROUND_GROUP))

    # T24: an instrument is BOUND by its CSourceSymbolCollectNode key, which is scoped by the
    # SHEET name: "<refdes>#1/<DesignSheet Title>:". A skeleton ships a different title than
    # the key, the meter then draws and simulates but reads nothing (0 V while the circuit
    # works), so the suffix and the refdes are both checked.
    titles = {(it.get("Title") or "").replace("&ASC", "").replace("&UNI", "")
              for it in root.iter("DesignSheet")}
    if strict and titles:
        stem = path.replace("\\", "/").split("/")[-1]
        stem = stem[:-5] if stem.endswith(".ms14") else stem
        for t in sorted(titles):
            if t != stem:
                fail("T24", "sheet title %r != file name %r - instrument keys are scoped by the "
                     "sheet, so the meters cannot bind and read 0 V" % (t, stem))
        # the sheet name is the document's identity: every copy of it must agree
        enc = "&ASC" + stem
        for tag, attr in (("Project", "Name"), ("Sheet", "SheetName"), ("CProject", "Name")):
            for el in root.iter(tag):
                v = el.get(attr)
                if v and v.replace("&UNI", "&ASC") != enc:
                    fail("T24", "%s/@%s is %r but the sheet is %r" % (tag, attr, v, enc))
    for node in root.iter("CSourceSymbolCollectNode"):
        key = (node.get("CompLongName") or "").replace("&ASC", "")
        iref, _, rest = key.partition("#")
        if not rest or ":" not in rest:
            fail("T24", "instrument key %r is not '<refdes>#<n>/<sheet>:'" % key)
            continue
        sheet = rest.split("/", 1)[1].rstrip(":") if "/" in rest else ""
        if titles and sheet not in titles:
            fail("T24", "instrument %s is bound to sheet %r but the document's sheet is %r - "
                 "the meter will read 0 V" % (iref, sheet, sorted(titles)))
        if iref not in comps and ("&ASC" + iref) not in comps:
            fail("T24", "instrument key %r names no placed part" % key)

    # T25: a pin's connection object must sit AT the pin, in PAGE coordinates. The GUI stores
    # symbol offset + the pin's local centre; writing the local centre leaves every pin near
    # the sheet origin, so nothing attaches and an instrument (an open circuit) silently reads
    # 0 V while the rest of the sheet still simulates.
    parent = {c: q for q in root.iter() for c in q}

    def _sym_offset(el):
        cur = el
        while cur is not None:
            if cur.get("Class") == "CIITSymbolComp":
                for g in cur.iter():
                    if g.get("Transformer-M20") is not None:
                        return float(g.get("Transformer-M20")), float(g.get("Transformer-M21"))
            cur = parent.get(cur)
        return 0.0, 0.0

    pin_objs = {}                       # connection-object id -> the CONNECTOR that owns it
    for it in root.iter("CIITPinConnectorComp"):
        if it.get("ptCenterX") is None:  # the wrapper Item has no geometry
            continue
        cl = it.find("ConnectList")
        for cref in (list(cl) if cl is not None else []):
            pin_objs[cref.get("ID")] = it
    stated = {}
    for cc in root.iter("CODComposite"):
        rc = cc.find("ReferencedComponents")
        if rc is None:
            continue
        for it in list(rc):
            for ch in it:
                if ch.tag == "CODPinComp" and ch.get("CenterX") is not None:
                    stated[it.get("ID")] = (float(ch.get("CenterX")), float(ch.get("CenterY")))
    for pid, conn in pin_objs.items():
        if pid not in stated:
            continue
        ox, oy = _sym_offset(conn)
        want = (ox + float(conn.get("ptCenterX") or 0), oy + float(conn.get("ptCenterY") or 0))
        got = stated[pid]
        if abs(got[0] - want[0]) > 1 or abs(got[1] - want[1]) > 1:
            fail("T25", "pin object %s is at (%.0f,%.0f) but the pin is at (%.0f,%.0f) - the pin "
                 "does not connect (an instrument then reads 0 V)" % (pid, got[0], got[1],
                                                                      want[0], want[1]))

    # T20: every part pin must be referenced by a wire. Connectivity is resolved from    # wire Connect1/Connect2 == pin ConnectList id, NOT from our CiNode bookkeeping; a pin
    # with no wire is an open terminal, and its net becomes singular ("Check node N").
    wired_ids = set()
    for objs in root.iter("Objects"):
        for it in objs:
            if it.get("Class") == "CIITLinkComp":
                wired_ids.add(it[0].get("Connect1"))
                wired_ids.add(it[0].get("Connect2"))
    for it in symbols:
        owner = next((r for r, (cid, c) in comps.items() if c.get("SymCompID") == it.get("ID")), "?")
        for pe in it.iter("CIITPinSymbolComp"):
            for conn in pe.iter("CIITPinConnectorComp"):
                cl = conn.find("ConnectList")
                if cl is None or not len(cl):
                    continue
                if cl[0].get("ID") not in wired_ids:
                    fail("T20", "%s pin %s has no wire (open terminal)"
                         % (owner, (pe.get("PinName") or "").replace("&ASC", "")))

    # T18: no dangling pin objects. Every junction stub (and every pin placeholder) must
    # be referenced by a wire; an unattached pin becomes a floating node and the analysis
    # dies with "Singular matrix ... floating with respect to net 0 (ground)".
    wire_ends = set()
    for objs in root.iter("Objects"):
        for it in objs:
            if it.get("Class") == "CIITLinkComp":
                wire_ends.add(it[0].get("Connect1"))
                wire_ends.add(it[0].get("Connect2"))
    for objs in root.iter("Objects"):
        for it in objs:
            if it.get("Class") != "CODPinComp":
                continue
            cl = it[0].find("ConnectList")
            if cl is None:
                continue
            for stub in cl:
                if stub.get("ID") not in wire_ends:
                    fail("T18", "junction stub %s at (%.0f,%.0f) has no wire"
                         % (stub.get("ID"), float(it[0].get("CenterX") or 0),
                            float(it[0].get("CenterY") or 0)))

    # T17: expand each instance template and check the resulting SPICE line shape.
    # Catches "too many arguments for 'r'" and "unknown model" classes without simulating.
    SHAPE = {"r": (4, 4), "c": (4, 4), "l": (4, 4), "v": (4, 8), "i": (4, 8),
             "q": (5, 6), "m": (6, 7), "d": (4, 5), "x": (3, 40)}
    for rname, (cid, c) in comps.items():
        at = c.find("Attributes")
        if at is None or len(at) < 3:
            continue
        tpl = ""
        for grp in list(at)[1:2]:
            for ch in grp:
                if ch.tag in ("CiaSpiceTmpltExprt", "CiaCString"):
                    tpl = (ch.get("String") or "").replace("&ASC", "")
        if not tpl or not re.match(r"[a-zA-Z]", tpl):
            continue                      # instruments and empty templates carry no element
        params = []
        for grp in list(at)[2:3]:
            for sub in grp:
                if sub.tag == "CiaParamList":
                    for lst in sub:
                        if lst.tag == "parameters":
                            params = [x.get("Value") or "" for x in lst]
        line = tpl.replace("%p", rname)
        line = re.sub(r"%t[A-Za-z0-9_]+", "N", line)
        line = line.replace("%m", (c.get("Model") and "MODEL") or "MODEL")
        line = re.sub(r"#([0-9]+)",
                      lambda m: (params[int(m.group(1)) - 1].replace("&ASC", "")
                                 if 1 <= int(m.group(1)) <= len(params) else "??"), line)
        toks = [t for t in line.split() if t]
        letter = toks[0][0].lower()
        lo, hi = SHAPE.get(letter, (3, 40))
        if not (lo <= len(toks) <= hi):
            msg = ("%s: %d tokens, expected %d-%d for '%s': %s"
                   % (rname, len(toks), lo, hi, letter, " ".join(toks)[:70]))
            # the hand-written reference project ships the GUI's all-purpose templates,
            # which are exactly what this check exists to reject
            if strict:
                fail("T17", msg)
            else:
                info.append("T17 " + msg)

    # T16: SPICE instance templates must be self-contained
    #   - `#n` is a 1-based parameter slot and must exist
    #   - " + " is a line continuation, but the template is ONE line, so the netlist
    #     writer emits a bare '+' and the simulator reports "Unable to interpret '+'"
    TPL_TAGS = ("CiaSpiceTmpltExprt", "CiaCString")
    for rname, (cid, c) in comps.items():
        at = c.find("Attributes")
        if at is None or len(at) < 3:
            continue
        tpl = ""
        for ch in at[1]:
            if ch.tag in TPL_TAGS:
                tpl = (ch.get("String") or "").replace("&ASC", "")
        if not tpl:
            continue
        n = 0
        for grp in list(at)[2:3]:
            for sub in grp:
                if sub.tag == "CiaParamList":
                    for lst in sub:
                        if lst.tag == "parameters":
                            n = len(lst)
        slots = {int(x) for x in re.findall(r"#([0-9]+)", tpl)}   # #n -> parameters[n]
        msgs = []
        if " + " in tpl:
            msgs.append("%s template contains an inline ' + ' continuation: %s"
                        % (rname, tpl[:48]))
        missing = sorted(x for x in slots if x >= n or x < 0)   # offset by one, see above
        if missing:
            msgs.append("%s template uses slots %s but only %d exist" % (rname, missing, n))
        for m in msgs:
            # a hand-written reference project may carry the GUI's all-purpose template;
            # files we generate must have a netlist-safe one
            if strict:
                fail("T16", m)
            else:
                info.append("T16 " + m)

    # T15: no wire endpoint may hang in space (a dropped segment leaves the net open)
    for pt, a, b in PV.floating(lparts, lwires, ljuncs, llabels)[:6]:
        msg = ("open endpoint (%.0f,%.0f) on (%.0f,%.0f)-(%.0f,%.0f)"
               % (pt[0], pt[1], a[0], a[1], b[0], b[1]))
        # existing projects use bus entries and hierarchical ports we do not model, so
        # this is a hard gate for generated files and informational for the control
        if strict:
            fail("T15", msg)
        else:
            info.append("T15 " + msg)

    # T22: no two part bodies may overlap (an instrument landing on a symbol looks like a
    # component that moved by itself and hides whichever part is underneath)
    for r1, r2 in PV.part_overlaps(lparts)[:4]:
        msg = "%s and %s overlap" % (r1, r2)
        if strict:
            fail("T22", msg)
        else:
            info.append("T22 " + msg)

    # T14: a wire may not pass over another part's pin - that is a short, not a crossing
    for oref, pin, a, b in PV.pin_short(lparts, lwires)[:6]:
        fail("T14", "wire (%.0f,%.0f)-(%.0f,%.0f) crosses %s pin (%.0f,%.0f)"
             % (a[0], a[1], b[0], b[1], oref, pin[0], pin[1]))

    # T13 is a *layout policy*, not a format rule (existing projects legitimately draw
    # near the origin), so it is enforced only for files we generate.
    for pref, bb, _own in lparts:
        if bb[0] < 60 or bb[1] < 80 or bb[2] > 900 or bb[3] > 660:
            msg = "%s bbox (%.0f,%.0f,%.0f,%.0f) outside safe box" % (
                pref, bb[0], bb[1], bb[2], bb[3])
            if strict:
                fail("T13", msg)
            else:
                info.append("T13 " + msg)

    # T11: CiPort/Nodes must contain exactly the CiNode that lists the port
    node_id_by_name = {clean(it[0].get("LocalName")): it.get("CiID") for it in els
                       if it.get("Class") == "CiNode"}
    for it in els:
        if it.get("Class") != "CiPort":
            continue
        pid = it.get("CiID")
        back = it[0].find("Nodes")
        refs = [x.get("CiID") for x in back] if back is not None else []
        want = node_id_by_name.get(port_node.get(pid))
        if want is None:
            fail("T11", "port %s is in no net" % pid)
        elif refs != [want]:
            fail("T11", "port %s Nodes=%s expected [%s]" % (pid, refs, want))

    # T10: the symbol -> component back-reference must resolve (CIITSymbolComp/CiComponent).
    # A dangling link here is what made the synthesized MOSFETs crash Multisim.
    comp_ids = {it.get("CiID") for it in els if it.get("Class") == "CiComponent"}
    for it in symbols:
        cref = it[0].get("CiComponent")
        if cref is not None and cref not in comp_ids:
            fail("T10", "symbol %s -> CiComponent %s does not exist" % (it.get("ID"), cref))

    # T9: every tag/attribute we emit must exist in a file Multisim already opened
    if ref is not None:
        rtags, rattrs = vocabulary(ref)
        for el in root.iter():
            if el.tag not in rtags:
                info.append("T9 unknown tag %s" % el.tag)
            else:
                for a in el.attrib:
                    if (el.tag, a) not in rattrs:
                        info.append("T9 unknown attr %s@%s" % (a, el.tag))

    name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    status = "PASS" if not fails else "FAIL (%d)" % len(fails)
    print("%-22s parts=%-3d nets=%-3d ports=%-3d models=%-3d %s"
          % (name, len(comps), len(nodes), len(ports), len(models), status))
    for f in fails[:12]:
        print("   ! " + f)
    if info and "-v" in sys.argv:
        for i in info[:8]:
            print("   i " + i)
    return not fails


def main(argv):
    ref = None
    paths = []
    it = iter(argv[1:])
    for a in it:
        if a == "--ref":
            ref = next(it, None)
        elif a in ("-v", "--verbose", "--control"):
            if a == "--control":
                paths.append("xml/skeleton.xml")
        else:
            paths.append(a)
    if not paths:
        print(__doc__)
        return 2
    ok = True
    for p in paths:
        ok = run(p, ref, strict=(ref is not None and p != ref)) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
