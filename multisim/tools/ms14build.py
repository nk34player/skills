"""Build Multisim .ms14 schematics by cloning real parts out of a donor project.

Everything here is derived from studying real Multisim 14.x files, see Multisim-skill.md.

Model (per schematic sheet, inside Project/UniqueSheets/.../CIITHierDoc/Diagram/CIITDiagram):
    Elements/Item[@Class=CiComponent]  placed part: attributes 0..52, Ports -> CiPort CiIDs
    Elements/Item[@Class=CiPort]       one per pin, Attributes[7] = CiaNodeType, Nodes -> CiNode
    Elements/Item[@Class=CiModel]      one per SPICE model used by the part
    Elements/Item[@Class=CiNode]       one per net, LocalName = net name, Ports -> CiPort CiIDs
    Elements/Item[@Class=CiCircuit]    index of Models/Nodes/Components CiIDs
    Components/CODComposite/Objects    symbol per instance (ID == CiComponent.SymCompID)
                                       holds Transformer-M20/M21 = absolute position in 1/1000 in
                                       pin symbols carry ConnectList -> CODPinComp ID (wire endpoint)
    Components/CODComposite/ReferencedComponents/Item[@Class=CODPinComp]  wire endpoints
    wire = CIITLinkComp with Connect1/Connect2 = CODPinComp IDs, Node = CiNode CiID,
           NodeText = CODNodeTextComp ID, Points/Item = absolute polyline
"""

import copy
import re
import uuid
import xml.etree.ElementTree as ET

import multisim_db

ID_ATTRS = {
    "ID", "CiID", "PortID", "CiComponent", "Component", "SymCompID", "Model", "Circuit",
    "Scope", "Node", "NodeText", "Connect1", "Connect2",
}


class Palette:
    """Indexes a real project file so parts can be cloned out of it."""

    def __init__(self, path):
        self.root = ET.parse(path).getroot()
        self.doc = next(self.root.iter("CIITHierDoc"))
        self.diagram = next(self.doc.iter("CIITDiagram"))
        self.elements = self.diagram.find("Elements")
        self.comp_objects = self.diagram.find("Components/CODComposite/Objects")
        self.ref_objects = self.diagram.find("Components/CODComposite/ReferencedComponents")
        self.circuit = None
        for it in self.elements:
            if it.get("Class") == "CiCircuit":
                self.circuit = it
        self.wire_proto = None
        self.label_proto = None
        self.junction_proto = None
        for objs in self.root.iter("Objects"):
            links = [i for i in objs if i.get("Class") == "CIITLinkComp"]
            labels = [i for i in objs if i.get("Class") == "CODNodeTextComp"]
            for j in objs:
                if j.get("Class") == "CODPinComp" and len(j) and                         j[0].find("ConnectList") is not None:
                    self.junction_proto = copy.deepcopy(j)
            if links and labels:
                self.wire_proto = copy.deepcopy(links[0])
                self.label_proto = copy.deepcopy(labels[0])
                break
        self.instrument_data = {}
        for node in self.root.iter("CSourceSymbolCollectNode"):
            name = (node.get("CompLongName") or "").replace("&ASC", "")
            self.instrument_data[name.split("#")[0]] = copy.deepcopy(node)
        self.components = {}
        for it in self.elements:
            if it.get("Class") != "CiComponent":
                continue
            c = it[0]
            name = c.get("LocalName")
            if name:
                self.components[name] = it

        # Multi-sheet donors keep a component's symbol in a *different* diagram than
        # the one holding the CiComponent (samples such as ClassBPushPullAmp store the
        # symbols on a second page). Index every Objects collection document-wide so
        # add_part() can find the symbol wherever it lives.
        self.symbol_index = {}
        for objs in self.root.iter("Objects"):
            for obj in objs:
                oid = obj.get("ID")
                if oid and oid not in self.symbol_index:
                    self.symbol_index[oid] = obj

    def refdes_list(self):
        return sorted(k for k in self.components)

    def part_of(self, item):
        """('RESISTOR_VIRTUAL', 'R', 2008) - database name, refdes prefix, type id."""
        c = item[0]
        attrs = c.find("Attributes")
        db = prefix = ""
        if len(attrs) > 4 and len(attrs[4]):
            vals = [_clean(x.get("Value", "")) for x in attrs[4][0].iter("Item")]
            db = vals[1] if len(vals) > 1 else ""
        if len(attrs) > 5 and len(attrs[5]):
            vals = [_clean(x.get("Value", "")) for x in attrs[5][0].iter("Item")]
            for v in vals:
                if v and "%d" in v:
                    prefix = v.split("%")[0]
                    break
        return db, prefix

    def pick_refdes(self, prefix, index=0):
        """Pick by refdes prefix ('XMM' for multimeters) when the part has no database name."""
        hits = [k for k, v in self.components.items() if self.part_of(v)[1] == prefix]
        if not hits:
            raise KeyError("no part with refdes prefix %s in palette %s" % (prefix, self.refdes_list()))
        return hits[index]

    def pick(self, db_name, index=0):
        hits = [k for k, v in self.components.items() if self.part_of(v)[0] == db_name]
        if not hits:
            raise KeyError("part %s not in palette %s" % (db_name, self.refdes_list()))
        return hits[index]


def _clean(v):
    for pre in ("&ASC", "&UNI"):
        if v.startswith(pre):
            v = v[len(pre):]
    return v


def _strip_ns(tag):
    return tag.split("}")[-1]


class Builder:
    def __init__(self, skeleton_xml, palette=None):
        self.wire_proto = copy.deepcopy(palette.wire_proto) if palette and palette.wire_proto else None
        self.junction_proto = copy.deepcopy(palette.junction_proto) if palette and palette.junction_proto else None
        self.label_proto = copy.deepcopy(palette.label_proto) if palette and palette.label_proto else None
        self.root = ET.fromstring(skeleton_xml)
        self.doc = next(self.root.iter("CIITHierDoc"))
        self.diagram = next(self.doc.iter("CIITDiagram"))
        self.elements = self.diagram.find("Elements")
        self.comp_objects = self.diagram.find("Components/CODComposite/Objects")
        self.ref_objects = self.diagram.find("Components/CODComposite/ReferencedComponents")
        self.circuit = next(it for it in self.elements if it.get("Class") == "CiCircuit")[0]
        self.node_attrs_proto = self._node_attrs_template()
        self.instrument_data = {}
        self._inst_proto = palette.instrument_data if palette else {}
        self.inst_data = self.doc.find("InstrumentsData")
        if self.inst_data is None:
            self.inst_data = ET.SubElement(self.doc, "InstrumentsData")
        self.next_id = 500000000
        self.parts = []
        self._lanes = {"h": [], "v": []}
        self._wire_sigs = set()
        self._pt_net = {}                # (x,y) -> CiNode that owns a wire end/junction
        self._net_labels = {}            # CiNode CiID -> the single net-name label object
        self._meter_segs = {}            # id(part) -> leads already drawn from it
        self._segs = []                  # (net, a, b) for every wire drawn so far
        self.circuit_id = self._circuit_ciid()
        # The instrument block is scoped by the SHEET name: Multisim binds a meter only when
        # `CSourceSymbolCollectNode@CompLongName == "<refdes>#1/<sheet title>:"`. The skeleton
        # ships a different title (Skeleton) than the hard-coded "Project" suffix, so
        # the block never bound and every meter read 0 V with the simulation running fine.
        sheet = next(self.root.iter("DesignSheet"), None)
        title = sheet.get("Title") if sheet is not None else None
        for pre in ("&ASC", "&UNI"):        # names are string-encoded; keys are plain
            if title and title.startswith(pre):
                title = title[len(pre):]
                break
        self.sheet_name = title or "Project"

    # ---------------------------------------------------------------- ids ----
    def _id(self):
        self.next_id += 1
        return str(self.next_id)

    def _remap(self, node, mapping):
        for el in node.iter():
            for attr in list(el.attrib):
                if attr == "InstanceID":
                    base = el.get(attr) or ""
                    mapping.setdefault(base, "{%s}" % str(uuid.uuid4()).upper())
                    el.set(attr, mapping[base])
                elif attr in ID_ATTRS:
                    old = el.get(attr)
                    if not old:
                        continue
                    if old not in mapping:
                        mapping[old] = self._id()
                    el.set(attr, mapping[old])

    # ------------------------------------------------------------- strip -----
    def clear(self):
        """Remove every placed part / net / wire, leaving an empty sheet.

        The CiCircuit item must survive: Nodes/Models/Components hang off it, and
        self.circuit points into it. Removing it silently detaches those lists and the
        saved file ends up with no circuit at all (Multisim then fails on open).
        """
        for it in list(self.elements):
            if it.get("Class") != "CiCircuit":
                self.elements.remove(it)
        for it in list(self.comp_objects):
            self.comp_objects.remove(it)
        for it in list(self.ref_objects):
            self.ref_objects.remove(it)
        for child in list(self.circuit):
            if child.tag in ("Models", "Nodes", "Components", "Probes", "CompAddRefs"):
                for it in list(child):
                    child.remove(it)
        # Instrument bindings live outside the Elements list, so they survive the purge
        # above. One left behind names a component that no longer exists ("C5 unbound
        # instrument") and points the meter's symbol at an id nothing owns.
        # The template's design net container carries net-label objects ("VCC", "GND").
        # Multisim takes a net's *name* from those labels, so a leftover "GND" renames the
        # ground net and net "0" stops existing: the netlist check then warns "No ground
        # node was found in your circuit", there is no reference node, every node floats
        # and the solver reports "Singular matrix. Check node N" - with N wandering
        # between runs because it is just the first floating node it meets.
        for cont in self.root.iter("CDesignNetContainer"):
            for nl in cont:
                if nl.tag != "NetLabels":
                    continue
                # keep the container and its wrapper item; purge only the per-net records,
                # which are rebuilt for this sheet's own nets at save time (a leftover record
                # renames a net - a stale "GND" makes net 0 disappear).
                for it in list(nl):
                    for holder in list(it):
                        if holder.tag == "Items":
                            for rec in list(holder):
                                if rec.get("Class") == "CSchDesignNetLabel":
                                    holder.remove(rec)
        for holder in list(self.root.iter("InstrumentsData")) +                 list(self.root.iter("Objects")):
            for it in list(holder):
                if it.get("Class") == "CSourceSymbolCollectNode":
                    holder.remove(it)
        self.parts = []

    def _circuit_ciid(self):
        """The id of the sheet's one CiCircuit - every object must point at it.

        Real files carry the same id on CiComponent/@Circuit, CiNode/@Circuit and
        CiModel/@Scope. A part pointing at an id that exists nowhere belongs to no
        circuit: the drawing still looks perfect, but the simulator nets nothing and
        every instrument reads 0 V.
        """
        for it in self.elements:
            if it.get("Class") == "CiCircuit" and it.get("CiID"):
                return it.get("CiID")
        for it in self.root.iter("Item"):
            if it.get("Class") == "CiCircuit" and it.get("CiID"):
                return it.get("CiID")
        return None

    def _stamp_circuit(self):
        """Point every part, net and model at the sheet's one CiCircuit.

        Only these three carry a circuit reference - ERC_CHK_OPTIONS/@Scope is an ERC
        setting ("0"), not an id, and stamping it over breaks the option block.
        """
        if not self.circuit_id:
            return
        for it in self.elements:
            cls = it.get("Class")
            for el in it.iter():
                if cls in ("CiComponent", "CiNode") and el.get("Circuit") is not None:
                    el.set("Circuit", self.circuit_id)
                elif cls == "CiModel" and el.get("Scope") is not None:
                    el.set("Scope", self.circuit_id)

    def _prune_models(self):
        """Drop CiModels no component references.

        A part cloned for its glyph brings its own card; borrowing another card then
        leaves the clone's behind. Two models with one LocalName is worse than untidy -
        the netlist's subckt name becomes ambiguous, so a voltmeter can end up resolving
        to the ammeter card (10 uOhm across its terminals) and read 0 V.
        """
        used = {c.get("Model") for c in
                (it[0] for it in self.elements if it.get("Class") == "CiComponent")}
        keep = []
        for it in list(self.elements):
            if it.get("Class") == "CiModel" and it.get("CiID") not in used:
                self.elements.remove(it)
                continue
            keep.append(it)
        models = self.circuit.find("Models")
        for r in list(models):
            if r.get("CiID") not in used:
                models.remove(r)

    def _sync_circuit_refs(self):
        """Rebuild CiCircuit/Components|Models|Nodes from the live element list.

        These lists are the circuit's membership: an id that names nothing (a model
        dropped during cleanup) or a model filed under Components (donor files list only
        CiComponents there) is a dangling reference - the kind of thing that makes the
        simulator build a netlist that does not match the drawing.
        """
        for tag, cls in (("Components", "CiComponent"), ("Models", "CiModel"),
                         ("Nodes", "CiNode")):
            lst = self.circuit.find(tag)
            if lst is None:
                continue
            for it in list(lst):
                lst.remove(it)
            for it in self.elements:
                if it.get("Class") == cls and it.get("CiID"):
                    ET.SubElement(lst, "Item").set("CiID", it.get("CiID"))

    def _dedupe_models(self):
        """One CiModel per subckt name, and every name unique.

        Each MOSFET clone brings its own copy of the same card, so a 6-transistor gate
        emitted the same .subckt three times. Identical cards are merged (and all
        components repointed); a name clash with a *different* card is renamed.
        """
        by_name, remap = {}, {}
        for it in list(self.elements):
            if it.get("Class") != "CiModel":
                continue
            name = it[0].get("LocalName") or ""
            card = _model_card(it)
            first = by_name.get(name)
            if first is None:
                by_name[name] = (it, card)
                continue
            if first[1] == card:
                remap[it.get("CiID")] = first[0].get("CiID")     # same card: share it
                self.elements.remove(it)
                continue
            new = name + "_%d" % (len(by_name) + 1)              # same name, other card
            it.set("LocalName", new)
            if len(it):
                it[0].set("LocalName", new)
            by_name[new] = (it, _model_card(it))

        if remap:
            for it in self.elements:
                if it.get("Class") == "CiComponent" and it[0].get("Model") in remap:
                    it[0].set("Model", remap[it[0].get("Model")])
            models = self.circuit.find("Models")
            live = {r.get("CiID") for r in models}
            for r in list(models):
                if r.get("CiID") not in live and r.get("CiID") not in {v for v in remap.values()}:
                    models.remove(r)
            present = {r.get("CiID") for r in models}
            for cid in set(remap.values()):
                if cid not in present:
                    m = ET.SubElement(models, "Item")
                    m.set("CiID", cid)

    # -------------------------------------------------------------- parts ----
    def add_part(self, palette, src_name, x, y, refdes=None, value=None):
        """Clone a part from a Palette and place it (1/1000 inch coordinates)."""
        src_item = palette.components[src_name]
        src_comp = src_item[0]
        mapping = {}

        new_item = copy.deepcopy(src_item)
        self._remap(new_item, mapping)
        new_comp = new_item[0]

        ports = []
        for ref in new_comp.find("Ports"):
            pid = ref.get("CiID")
            for it in palette.elements:
                if it.get("Class") == "CiPort" and it.get("CiID") in mapping and mapping[it.get("CiID")] == pid:
                    pit = copy.deepcopy(it)
                    self._remap(pit, mapping)
                    self.elements.append(pit)
                    ports.append(pit)
                    break
        if not ports:  # fall back: original ciid order
            for ref in src_comp.find("Ports"):
                old = ref.get("CiID")
                for it in palette.elements:
                    if it.get("Class") == "CiPort" and it.get("CiID") == old:
                        pit = copy.deepcopy(it)
                        self._remap(pit, mapping)
                        self.elements.append(pit)
                        ports.append(pit)
                        break

        models = []
        mid = src_comp.get("Model")
        for it in palette.elements:
            if it.get("Class") == "CiModel" and it.get("CiID") == mid:
                mit = copy.deepcopy(it)
                self._remap(mit, mapping)
                self.elements.append(mit)
                models.append(mit)
                for ref in self.circuit.find("Models"):
                    if ref.get("CiID") == mit.get("CiID"):
                        break
                else:
                    m = ET.SubElement(self.circuit.find("Models"), "Item")
                    m.set("CiID", mit.get("CiID"))
                break

        sym_src = palette.symbol_index.get(src_comp.get("SymCompID"))
        if sym_src is None:
            sym_src = next(it for it in palette.comp_objects
                           if it.get("ID") == src_comp.get("SymCompID"))
        sym = copy.deepcopy(sym_src)
        self._remap(sym, mapping)
        sym[0].set("Transformer-M20", str(x))
        sym[0].set("Transformer-M21", str(y))
        self.comp_objects.append(sym)

        # pin placeholders referenced by the wires of this symbol. Each one is a REAL
        # CODPinComp object carrying CenterX/CenterY: the sheet resolves a connection from
        # that position, so a bare <Item Class="CODPinComp" ID=.../> with no payload
        # leaves every pin unplaced - the netlist still checks clean and the run dies with
        # "Singular matrix ... floating with respect to net 0" (one net per pin).
        # The connection object carries PAGE coordinates: symbol offset + the pin's local
        # centre (a GUI-saved part proves it: local (81,54) on a symbol at (288,279) is stored
        # as (369,333)). Local coordinates put every pin near the sheet origin, so nothing
        # attaches - and an open instrument still reads a perfectly happy `0`.
        for conn in sym.iter("CIITPinConnectorComp"):
            cl = conn.find("ConnectList")
            if cl is None:
                continue
            lx = float(conn.get("ptCenterX") or 0)
            ly = float(conn.get("ptCenterY") or 0)
            for it in cl:
                pid = it.get("ID")
                if pid and not any(r.get("ID") == pid for r in self.ref_objects):
                    self._ref_pin(pid, x + lx, y + ly)

        self.elements.append(new_item)
        if new_comp.get("Model"):
            self.circuit.find("Components").append(_ref(new_comp.get("Model")))
        comp_ref = ET.SubElement(self.circuit.find("Components"), "Item")
        comp_ref.set("CiID", new_item.get("CiID"))

        if refdes:
            self._set_refdes(new_comp, sym, refdes)
        elif not (new_comp.get("LocalName") or "").startswith("&"):
            self._set_refdes(new_comp, sym, new_comp.get("LocalName") or "")
        if value is not None:
            self._set_value(palette, new_comp, sym, src_name, value)

        part = Part(self, new_comp, sym)
        self.parts.append(part)
        self._rebuild_node_refs()
        return part

    @staticmethod
    def _num(value):
        """'10k' -> 10000, '1.6k' -> 1600, '2.2M' -> 2200000, '5' -> 5."""
        m = re.match(r"\s*(-?[0-9.]+)\s*([a-zA-Z]*)", str(value))
        if not m:
            return 0
        mult = {"": 1, "k": 1e3, "K": 1e3, "meg": 1e6, "M": 1e6, "m": 1e-3,
                "u": 1e-6, "n": 1e-9, "p": 1e-12}.get(m.group(2), 1)
        return float(m.group(1)) * mult

    def set_spice_template(self, part, template):
        """Rewrite a part's SPICE instance template, leaving its parameters untouched.

        Multisim expands `template` verbatim into the netlist line: `%p` refdes,
        `%t<pin>` node, `%m` model, and `#n` = `parameters[n]` - note the offset: `#1` is
        the SECOND entry. Proven by two GUI-saved files (the donor's R1 shows 200k and
        stores it at `parameters[1]`, its stock template reads `#1`; the hand-drawn Q1
        does the same with 10k). Two things this implies, and both cause "simulation
        refuses to start" errors:

          * a `#n` must point at the slot that actually holds the value. Read one slot too
            far and the netlist gets 0 (a 0-ohm resistor makes the matrix singular) or a
            missing token, so the element is dropped;
          * a ` + ` inside the template is SPICE line continuation, but the template is a
            single line - the parser then sees a bare `+` operator.

        Never rewrite the slot list here: the editor takes the value it *displays* from
        that list, and resizing it makes every part show 0.
        """
        at = part.comp.find("Attributes")
        for grp in list(at)[1:2]:
            for g in grp:
                if g.tag in ("CiaSpiceTmpltExprt", "CiaCString"):
                    g.set("String", "&ASC" + template)
                    return part
        raise KeyError("part %s has no SPICE template attribute" % part.name)

    def _set_refdes(self, comp, sym, refdes):
        # Names are string-encoded in this format: every GUI-saved file stores
        # &ASC<name> ("&ASC0" IS the net name "0"). Writing a bare name breaks the one
        # place where a name is a lookup key - an instrument's InstrumentProperties is
        # keyed by "&ASC<refdes>#1/Project:", so a bare LocalName orphans the block and
        # the meter keeps its default 0 V display.
        comp.set("LocalName", "&ASC" + refdes)
        for t in sym.iter():
            if _strip_ns(t.tag) == "CIITSymTextCompName" or t.tag == "CIITSymTextCompName":
                t.set("Output", "&ASC" + refdes)

    def _set_value(self, palette, comp, sym, src_name, value):
        """Set the displayed value of a cloned part (R: "10k", V: "5V")."""
        src_comp = palette.components[src_name][0]
        attrs = comp.find("Attributes")
        src_attrs = src_comp.find("Attributes")
        params = attrs[2][0].find("parameters")
        src_params = src_attrs[2][0].find("parameters")

        if (src_params[1].get("Value") or "").startswith("&ASC"):
            # string encoded part (resistor, capacitor, ...)
            params[1].set("Value", "&ASC" + value)
            old = (src_attrs[41][0].get("String") or "").replace("&ASC", "")
            for idx in (41, 42):
                cur = attrs[idx][0].get("String")
                if cur:
                    attrs[idx][0].set("String", cur.replace("&ASC" + old, "&ASC" + value)
                                      .replace("&UNI" + old, "&UNI" + value))
        else:
            # numeric parameter part (sources, ...)
            num = re.match(r"-?[0-9.]+", value).group(0)
            old_num = src_params[1].get("Value")
            for i, it in enumerate(params):
                v = it.get("Value") or ""
                if v == old_num or v == "&ASC" + old_num:
                    it.set("Value", ("&ASC" if v.startswith("&ASC") else "") + num)
        # Every numeric parameter is mirrored in a `doubles` list that the editor renders
        # and the netlister may read. Leaving it stale keeps the DONOR's value (a 5 V source
        # still running at the donor's 8.7 V) while the string list looks right.
        lst = attrs[2][0]                      # this IS the CiaParamList
        if lst is not None:
            num = re.match(r"-?[0-9.]+", value).group(0)
            for sub in lst:
                if sub.tag == "doubles" and len(list(sub)) > 1:
                    item = list(sub)[1]
                    if item.get("Value") is not None:
                        item.set("Value", num)
                    if item.get("Double") is not None:
                        item.set("Double", num)
                    break

        # value text under the symbol
        for t in sym.iter("CIITSymTextCompValue"):
            out = t.get("Output") or ""
            if out.startswith("&UNI"):
                disp, _, suffix = out[4:].partition("_")
                t.set("Output", "&UNI" + value + "_" + suffix)
            elif out.startswith("&ASC"):
                m = re.match(r"&ASC(-?[0-9.]+)(.*)$", out)
                if m:
                    t.set("Output", "&ASC" + re.match(r"-?[0-9.]+", value).group(0) + m.group(2))

    # -------------------------------------------------------------- wires ----
    def _free_hub(self, pos, hub_j, all_parts, mine, step=8, reach=160):
        """Move a star hub off an already drawn wire, keeping it near its pin."""
        for off in range(step, reach + 1, step):
            for cand in ((hub_j[0], hub_j[1] - off), (hub_j[0], hub_j[1] + off),
                         (hub_j[0] - off, hub_j[1]), (hub_j[0] + off, hub_j[1])):
                if self._wire_clear(pos, cand, mine) and                         self._path_clear([pos, cand], all_parts, None, None):
                    return cand
        return hub_j

    def _wire_clear(self, a, b, mine):
        """Nothing already drawn may sit on this stretch.

        A crossing with another net is a short as far as the editor is concerned, and a
        same-net overlap is a doubled wire. Both are cheap to rule out before drawing a
        straight spur; the elbow does the same test as part of its cost.
        """
        for net, c, d in self._segs:
            if net == mine:
                if _seg_overlaps(a, b, c, d):
                    return False
            elif _seg_hits(a, b, c, d):
                return False
        return True

    def _free_column(self, axis, key, ys, coord, all_parts, reach=(0, 16, 24, 32, 40, 48, 64,
                                                                   80, 96, 112, 128, 160)):
        """A clear line for a shared trunk: the pins' own line first, else beside it."""
        lo, hi = min(ys + [coord]), max(ys + [coord])
        for off in reach:
            for cand in ((key,) if off == 0 else (key - off, key + off)):
                seg = [(cand, lo), (cand, hi)] if axis == "h" else [(lo, cand), (hi, cand)]
                if not self._path_clear(seg, all_parts, None, None):
                    continue
                # a trunk laid over an existing wire doubles it, and over another net's
                # wire it shorts the two nets together
                if any(_seg_overlaps(seg[0], seg[1], c, d) for _n, c, d in self._segs):
                    continue
                return cand
        return None

    def _lead_clear(self, pt, axis, channel, all_parts, part):
        """Is the short lead from a pin out to the trunk column clear?

        Bodies are not enough: a lead that runs along the row of another pin grazes it,
        and in Multisim a wire through a pin is a short. The neighbouring pins are tested
        too (the lead's own two ends are excluded).
        """
        end = (channel, pt[1]) if axis == "h" else (pt[0], channel)
        if abs(end[0] - pt[0]) < 1 and abs(end[1] - pt[1]) < 1:
            return True
        return self._path_clear([pt, end], all_parts, part, None,
                                self.pin_boxes(skip_pts=(pt, end)))

    def _trunk(self, ps, lead, bus_pt, spurs, axis, node, all_parts):
        """One vertical/horizontal trunk serving several stacked pins, one tap each.

        Each tap is a junction object (3 stubs: the lead plus the two trunk segments), and
        the trunk is drawn as segments *between* taps, so no two wires of this net ever
        cover the same stretch.
        """
        pts = [lead[p] for p in ps]                    # farthest first
        stubs = []
        for i, pt in enumerate(pts):
            if i == 0:                     # far end: a corner of exactly two wires
                corner = self._id()        # both wires must reference ONE object
                self._placeholder(corner, pt[0], pt[1])
                ids = [corner, corner]
            else:                          # a real tap: three wires meet, a junction
                ids = [self._id() for _ in range(3)]
                self._junction(pt[0], pt[1], ids, node)
            stubs.append(ids)
        for i, (part, pin) in enumerate(ps):
            self._wire(part.pin_pos(pin), pts[i], part.pin_conn(pin), stubs[i][0], node)
        for i in range(len(pts) - 1):
            self._wire(pts[i], pts[i + 1], stubs[i][1], stubs[i + 1][1], node)
        self._wire(pts[-1], bus_pt, stubs[-1][2], spurs[0], node)

    def _wire(self, pa, pb, c1, c2, node, label_at=None, label=True):
        """One orthogonal wire, cloned from a real donor wire + its net-label object."""
        pts = [pa, pb]
        if pa[0] != pb[0] and pa[1] != pb[1]:
            pts = [pa, (pb[0], pa[1]), pb]
        if self.wire_proto is None or self.label_proto is None:
            raise RuntimeError("Builder needs a palette with wire+label prototypes")

        # a net must never carry the same two-point segment twice (double-drawn wires
        # look like a short and confuse the schematic editor)
        kept = [p for p in pts if p not in (pa, pb)]
        sig = (node.get("CiID"), min(pa, pb), max(pa, pb))
        if sig in self._wire_sigs:
            return None
        self._wire_sigs.add(sig)

        link = copy.deepcopy(self.wire_proto)
        wid = self._id()
        link.set("ID", wid)
        e = link[0]
        e.set("Connect1", c1)
        e.set("Connect2", c2)
        e.set("Node", node.get("CiID"))
        for k in ("Transformer-M00", "Transformer-M01", "Transformer-M10",
                  "Transformer-M11", "Transformer-M20", "Transformer-M21"):
            e.attrib.pop(k, None)
        pts_el = e.find("Points")
        for it in list(pts_el):
            pts_el.remove(it)
        for (px, py) in pts:
            it = ET.SubElement(pts_el, "Item")
            it.set("X", str(int(round(px))))
            it.set("Y", str(int(round(py))))
        guid = e.find("ElectricalObject/ModifierInfo/Element/Item")
        if guid is not None:
            guid.set("Guid", "{%s}" % str(uuid.uuid4()).upper())

        # ONE label object per NET, linked to every wire of that net - a GUI-saved sheet
        # carries one per net (9 nets -> 9 labels), not one per wire segment.
        lab = self._net_labels.get(node.get("CiID"))
        if lab is None:
            lab = self._node_text(label_at or pa, wid)
            self._net_labels[node.get("CiID")] = lab
        elif label:
            links = lab[0].find("Links")
            if links is not None and not any(x.get("ID") == wid for x in links):
                it = ET.SubElement(links, "Item")
                it.set("ID", wid)
                it.set("Class", "CIITLinkComp")
        e.set("NodeText", lab.get("ID"))
        for a, b in zip(pts, pts[1:]):
            self._segs.append((node.get("CiID"), a, b))
        self._claim((int(round(pa[0])), int(round(pa[1]))), node)
        self._claim((int(round(pb[0])), int(round(pb[1]))), node)
        self.comp_objects.append(link)
        return link

    def _claim(self, pt, node):
        """Remember which net owns a wire end / junction point.

        Two nets meeting at one coordinate are joined by the editor's junction object and
        the nets silently merge - a meter wired that way reads 0 V because its node is
        shorted to the return.
        """
        self._pt_net.setdefault(pt, node.get("CiID"))

    def connect(self, part_a, pin_a, part_b, pin_b, net_name=None):
        """Wire two pins together (one net)."""
        return self.connect_net(net_name, [(part_a, pin_a), (part_b, pin_b)])

    def _junction(self, x, y, stubs, net):
        """Trunk junction: a CODPinComp at (x,y) owning a stub per attached wire.

        Real files (HW122) wire rails as one horizontal run plus short spurs, joined by
        these junction objects. Multisim needs the object; a plain crossing wire does not
        connect.
        """
        if self.junction_proto is None:
            raise RuntimeError("Builder needs a palette with a junction prototype")
        j = copy.deepcopy(self.junction_proto)
        j.set("ID", self._id())
        j[0].set("CenterX", str(int(round(x))))
        j[0].set("CenterY", str(int(round(y))))
        cl = j[0].find("ConnectList")
        for it in list(cl):
            cl.remove(it)
        for sid in stubs:
            it = ET.SubElement(cl, "Item")
            it.set("ID", sid)
            it.set("Class", "CODPinComp")
            stub = ET.Element("Item", {"ID": sid, "Class": "CODPinComp"})
            self.ref_objects.append(stub)
        self._claim((int(round(x)), int(round(y))), net)
        self.comp_objects.append(j)
        return j

    # ------------------------------------------------------------ geometry ----
    def part_bbox(self, part):
        """(x0, y0, x1, y1) of a placed part: pins + the symbol's own drawing."""
        xs, ys = [], []
        for info in part.pins().values():
            xs.append(info["pos"][0])
            ys.append(info["pos"][1])
        sx = float(part.sym[0].get("Transformer-M20") or 0)
        sy = float(part.sym[0].get("Transformer-M21") or 0)
        for el in part.sym.iter():
            if el.get("pt0X") is not None:
                xs += [sx + float(el.get("pt0X")), sx + float(el.get("pt1X") or 0)]
                ys += [sy + float(el.get("pt0Y")), sy + float(el.get("pt1Y") or 0)]
            if el.get("CenterX") is not None:
                r = float(el.get("Radius1") or 0)
                cx, cy = sx + float(el.get("CenterX")), sy + float(el.get("CenterY"))
                xs += [cx - r, cx + r]
                ys += [cy - r, cy + r]
        if not xs:
            return None
        return (min(xs) - 4, min(ys) - 4, max(xs) + 4, max(ys) + 4)

    def obstacles(self, skip=()):
        """[(part, box)] for every placed part except those in `skip`."""
        skip = {id(p) for p in skip}
        out = []
        for part in self.parts:
            if id(part) in skip:
                continue
            bb = self.part_bbox(part)
            if bb:
                out.append((part, bb))
        return out

    def pin_boxes(self, skip_pts=(), half=5):
        """Small boxes around every pin; a wire passing over one is a short, not a cross.

        Pins of the net being routed are skipped: a wire that reaches another pin of the
        *same* net is a connection, and refusing it forces a detour that then doubles back
        over the bus.
        """
        out = []
        mine = getattr(self, "_routing_pins", ())
        for part in self.parts:
            for info in part.pins().values():
                x, y = info["pos"]
                if any(abs(x - sx) <= 3 and abs(y - sy) <= 3 for sx, sy in skip_pts):
                    continue
                if any(abs(x - sx) <= 3 and abs(y - sy) <= 3 for sx, sy in mine):
                    continue
                out.append((x - half, y - half, x + half, y + half))
        return out

    @staticmethod
    def _hits(boxes, a, b):
        """True if the axis-aligned segment a->b crosses any box."""
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        for (bx0, by0, bx1, by1) in boxes:
            if x1 < bx0 or x0 > bx1 or y1 < by0 or y0 > by1:
                continue
            return True
        return False

    def _free_lane(self, axis, coord, span, boxes, pins=(), step=8, reach=320, gap=6,
                   net_node=None):
        """Choose a bus lane: no part box, no lane used by another net, and - the part
        that matters visually - no lane whose spurs would have to wrap around a part.

        Cost order: clear bus span, then fewest wrapped spurs, then distance from the
        requested coordinate. Without the spur term a lane just past a resistor looks
        like a wire looping around the component.
        """
        def hits(a, b, cand=None, mine=None):
            # a lane drawn on top of an existing wire is a doubled wire (and, if the
            # other wire belongs to another net, a short) - neither is a lane
            for _net, c, d in self._segs:
                if _seg_overlaps(a, b, c, d):
                    return True
            x0, x1 = sorted((a[0], b[0]))
            y0, y1 = sorted((a[1], b[1]))
            for (bx0, by0, bx1, by1) in list(boxes) + self.pin_boxes():
                if x1 <= bx0 or x0 >= bx1 or y1 <= by0 or y0 >= by1:
                    continue
                return True
            if cand is not None:
                # the lane creates a junction above/below every pin; one of those is
                # already another net's wire end -> the editor would merge the nets
                for _part, (px, py) in pins:
                    pt = (int(round(px if axis == "h" else cand)),
                          int(round(cand if axis == "h" else py)))
                    if self._pt_net.get(pt, mine) != mine:
                        return True
            return False

        def wrapped(cand):
            """Spurs that would have to cross a body to reach the lane.

            The pin's *own* part is excluded: leaving a pin outward legitimately crosses
            its outline at the pin itself, and counting that would make both sides of a
            component look equally bad (which is how a wire ends up looping around it).
            """
            n = 0
            for part, (px, py) in pins:
                if getattr(part, "instrument", False):
                    continue          # a meter sits in its own band; its spur is a
                                      # separate problem (judged by the junction check)
                jp = (px, cand) if axis == "h" else (cand, py)
                if abs(px - jp[0]) < 1 and abs(py - jp[1]) < 1:
                    continue                     # pin already on the lane
                own = self.part_bbox(part)
                if own:
                    # inset by 8: leaving a pin outward exits immediately, while a spur
                    # that runs to the far side of the body passes through the core
                    own = (own[0] + 8, own[1] + 8, own[2] - 8, own[3] - 8)
                rects = [r for r in boxes if r != self.part_bbox(part)] + [own]
                x0, x1 = sorted((px, jp[0]))
                y0, y1 = sorted((py, jp[1]))
                for (bx0, by0, bx1, by1) in rects:
                    if x1 <= bx0 or x0 >= bx1 or y1 <= by0 or y0 >= by1:
                        continue
                    n += 1
                    break
            return n

        mine = net_node.get("CiID") if net_node is not None else None
        best, best_cost = coord, None
        for k in range(0, reach // step + 1):
            for cand in ((coord,) if k == 0 else (coord - k * step, coord + k * step)):
                if any(abs(cand - used) < gap for used in self._lanes[axis]):
                    continue
                a, b = ((span[0], cand), (span[1], cand)) if axis == "h" else                        ((cand, span[0]), (cand, span[1]))
                cost = (1 if hits(a, b, cand, mine) else 0, wrapped(cand), abs(cand - coord))
                if best_cost is None or cost < best_cost:
                    best, best_cost = cand, cost
                    if cost[0] == 0 and cost[1] == 0:
                        self._lanes[axis].append(cand)
                        return cand
        self._lanes[axis].append(best)
        return best

    def _joint(self, x=None, y=None):
        """A wire-to-wire joint id (needs the positioned placeholder object real files carry)."""
        jid = self._id()
        self._placeholder(jid, x, y)
        return jid

    def _placeholder(self, jid, x=None, y=None):
        """Register an id as a referenced component.

        Every id a wire points at must exist somewhere in the file, or the netlister sees
        a connection to nothing (a dangling ref, and a floating node at simulation time).
        A junction owns its stubs; a corner between two wires has no junction object, so
        the two ids it allocates still have to be declared - with a position, or nothing
        can attach to them.
        """
        return self._ref_pin(jid, x, y)

    def _ref_pin(self, pid, cx=None, cy=None):
        """Declare a connection point as a positioned CODPinComp object.

        Wire endpoints and pin ConnectList entries name these ids. A GUI-saved sheet always
        defines them with a full payload (Class, CenterX, CenterY, ...) inside
        ReferencedComponents; an endpoint without coordinates cannot be placed, so the
        connection does not exist for the netlister.
        """
        r = ET.SubElement(self.ref_objects, "Item")
        r.set("ID", pid)
        r.set("Class", "CODPinComp")
        pin = ET.SubElement(r, "CODPinComp")
        pin.set("Class", "CODPinComp")
        pin.set("instID", "0")
        for k, v in (("Stretchable", "1"), ("Moveable", "1"), ("LabelSelectable", "1"),
                     ("Selectable", "1"), ("LockedPenColor", "0"), ("LockedBrushColor", "0"),
                     ("Layer", "511"), ("Text", ""), ("Internal", "0")):
            pin.set(k, v)
        if cx is not None:
            pin.set("CenterX", str(int(round(float(cx)))))
        if cy is not None:
            pin.set("CenterY", str(int(round(float(cy)))))
        for k, v in (("Mobility", "1"), ("Pen-Style", "5"), ("Pen-Width", "1"),
                     ("Pen-Color", "0"), ("Hidden", "0")):
            pin.set(k, v)
        return pid

    def _ref_bare(self, cls, oid):
        """Reference an object that is defined elsewhere, by its REAL class."""
        if not oid or any(r.get("ID") == oid for r in self.ref_objects):
            return oid
        r = ET.SubElement(self.ref_objects, "Item")
        r.set("ID", oid)
        r.set("Class", cls)
        return oid

    def _rebuild_ref_classes(self):
        """ReferencedComponents must index the sheet by class, not call everything a pin.

        Real sheets list bare refs as CIITLinkComp (wire), CIITPinConnectorComp (pin) and
        CODNodeTextComp (label); only connection *points* are CODPinComp. Tagging a wire as
        a pin makes the index disagree with the drawing.
        """
        typed = ("CIITLinkComp", "CIITPinConnectorComp", "CODNodeTextComp")
        # pin objects are nested inside their symbol, so they are collected separately
        nested = []
        for sym in self.comp_objects:
            for it in sym.iter("Item"):
                if it.get("Class") == "CIITPinConnectorComp" and it.get("ID"):
                    nested.append(it.get("ID"))
        for oid in nested:
            self._ref_bare("CIITPinConnectorComp", oid)
        for it in list(self.comp_objects):
            cls, oid = it.get("Class"), it.get("ID")
            if not oid or cls not in typed:
                continue
            for r in self.ref_objects:
                if r.get("ID") == oid:
                    r.set("Class", cls)
                    break
            else:
                self._ref_bare(cls, oid)

    def _stub_point(self, part, start, all_boxes=(), dist=14):
        """A point just outside the pin's body, in a direction that is actually free.

        A pin sits on its symbol border, so a wire leaving the "wrong" way runs back
        through the component; and a pin can sit a few units from a *neighbouring* part,
        so the preferred direction has to be validated, not assumed.
        """
        bb = self.part_bbox(part)
        if not bb:
            return start
        cx, cy = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
        dx, dy = start[0] - cx, start[1] - cy
        cands = [(bb[2] + dist, start[1]), (bb[0] - dist, start[1]),
                 (start[0], bb[3] + dist), (start[0], bb[1] - dist)]
        # preferred first: the face the pin actually points at
        cands.sort(key=lambda c: abs(c[0] - start[0]) + abs(c[1] - start[1])
                   if ((c[0] > start[0]) == (dx > 0) and c[1] == start[1]) or
                      ((c[1] > start[1]) == (dy > 0) and c[0] == start[0]) else 10 ** 6)
        rects = [r for p2, r in all_boxes if p2 is not part]
        for cand in cands:
            x0, x1 = sorted((start[0], cand[0]))
            y0, y1 = sorted((start[1], cand[1]))
            if any(not (x1 <= bx0 or x0 >= bx1 or y1 <= by0 or y0 >= by1)
                   for (bx0, by0, bx1, by1) in rects):
                continue
            return cand
        return cands[0]

    def _elbow(self, start, end, all_boxes, net_node, c_pin, c_bus,
               part=None, end_part=None, step=8, reach=760, bus_axis=None):
        """Route a pin to a net point with axis-aligned segments only.

        Obstacle policy: the first leg may touch the pin's own part, the last leg may
        touch the target part (a wire has to reach its pin), everything between avoids
        every body. L routes are tried before Z routes so the result stays readable.
        """
        stub = self._stub_point(part, start, all_boxes) if part is not None else start
        lead = [start, stub] if stub != start else []
        pin_rects = self.pin_boxes(skip_pts=(start, end))

        def chain(points):
            out = []
            for pt in points:
                if not out or pt != out[-1]:
                    out.append(pt)
            return out

        def candidates():
            """Yield axis-aligned paths, cheapest topology first.

            `origin` is the pin itself first: a stub is only needed when the direct
            routes would cross the pin's own body, and forcing it always produced
            needless zig-zags next to the lane.
            """
            for origin in ((start, stub) if stub != start else (start,)):
                pre = [start] if origin is stub else []       # pin -> stub must be drawn
                if abs(origin[0] - end[0]) < 1 or abs(origin[1] - end[1]) < 1:
                    yield pre + [origin, end]
                yield pre + [origin, (end[0], origin[1]), end]      # L via end's column
                yield pre + [origin, (origin[0], end[1]), end]      # L via end's row
            for origin in ((start, stub) if stub != start else (start,)):
                pre = [start] if origin is stub else []
                for off in range(step, reach + 1, step):
                    for sign in (-1, 1):
                        col = origin[0] + sign * off
                        yield pre + [origin, (col, origin[1]), (col, end[1]), end]
                        row = origin[1] + sign * off
                        yield pre + [origin, (origin[0], row), (end[0], row), end]
            # free column AND free row: needed when both the pin column and the target
            # row are blocked by other parts' pins
            inner = range(20, 260, 20)
            for origin in ((start, stub) if stub != start else (start,)):
                pre = [start] if origin is stub else []
                for off in range(step, reach + 1, step):
                    for sign in (-1, 1):
                        col = origin[0] + sign * off
                        for roff in inner:
                            for rsign in (-1, 1):
                                row = end[1] + rsign * roff
                                yield pre + [origin, (col, origin[1]), (col, row),
                                             (end[0], row), end]

        def two_channel():
            """Route round the pin's own body on one column, then approach square on.

            A pin on the far side of its symbol (its lead would cross the body) needs two
            channels: one to get clear, one to come back in line with the junction. Without
            this the router either crosses the body or descends the bus column and doubles
            the bus wire.
            """
            for col in (start[0] + d for d in (-16, 16, -24, 24, -32, 32, -48, 48, -64, 64,
                                               -96, 96, -128, 128, -160, 160, -200, 200)):
                for col2 in (end[0] + d for d in (16, -16, 24, -24, 32, -32, 48, -48, 64, -64)):
                    for roff in range(20, 261, 20):
                        for rsign in (-1, 1):
                            row = end[1] + rsign * roff
                            yield [start, (col, start[1]), (col, row), (col2, row),
                                   (col2, end[1]), end]

        def cost(pts):
            """Body violations first; only a body-clear route pays for the wire test.

            Wire-vs-wire is checked last because it is the expensive part, and because a
            route that already crosses a component is rejected regardless.
            """
            n = 0
            for i, (a, b) in enumerate(zip(pts, pts[1:])):
                if not self._path_clear([a, b], all_boxes,
                                        part if i == 0 else None,
                                        end_part if i == len(pts) - 2 else None,
                                        pin_rects):
                    n += 1
            if n:
                return (n, 0)                 # a body crossing outranks any wire clash
            m = 0
            doubled = 0
            mine = net_node.get("CiID")
            # a route that doubles back along its own column draws two wires on top of
            # each other (looks like a doubled wire, and merges when edited)
            for i in range(len(pts) - 1):
                for j in range(i + 2, len(pts) - 1):
                    if _seg_overlaps(pts[i], pts[i + 1], pts[j], pts[j + 1]):
                        doubled += 1
                        break
            for pt in pts[1:-1]:
                key = (int(round(pt[0])), int(round(pt[1])))
                if self._pt_net.get(key, mine) != mine:
                    m += 1                    # would join two nets at that corner
            for a, b in zip(pts, pts[1:]):
                for net, c, d in self._segs:
                    if net == mine:
                        # same net: touching is fine (that is the join), but running
                        # along a stretch that is already drawn doubles the wire
                        if _seg_overlaps(a, b, c, d):
                            doubled += 1   # a doubled wire is as bad as a body hit
                            break
                        continue
                    if _seg_hits(a, b, c, d):
                        m += 1                # crossing / T onto another net's wire
                        break
            # An instrument's two leads must not cross each other either: pin 1 is the
            # '+' and pin 2 the return, so a lead crossing the return reads as a short
            # across the meter even though the netlist is fine.
            # No leg may run along the bus line itself: it would be drawn on top of the
            # bus (the "doubled rail" look) and, if it descends the bus column, over the
            # spurs that already use it.
            line = end[1] if bus_axis == "h" else end[0]
            for a, b in zip(pts, pts[1:]):
                if bus_axis == "h" and abs(a[1] - b[1]) <= 2 and abs(a[1] - line) <= 2:
                    m += 2
                elif bus_axis == "v" and abs(a[0] - b[0]) <= 2 and abs(a[0] - line) <= 2:
                    m += 2
            for c, d in self._meter_segs.get(id(part), ()):
                for a, b in zip(pts, pts[1:]):
                    if _seg_hits(a, b, c, d):
                        m += 1
            return (doubled, m)

        best, best_cost = None, None
        tried = 0
        # cheap topologies first; the two-channel search is only needed for a pin whose
        # lead would cross its own body, and it is far more expensive to enumerate
        for mid in list(candidates()) + list(two_channel()):
            tried += 1
            if tried > 200000:
                break
            pts = chain(mid)
            c = cost(pts)
            if c == (0, 0):
                best, best_cost = pts, 0
                break
            if best_cost is None or c < best_cost:
                best, best_cost = pts, c

        pts = best if best else chain([start, end])    # best effort, always connected
        if part is not None and getattr(part, "instrument", False):
            self._meter_segs.setdefault(id(part), []).extend(zip(pts, pts[1:]))
        conns = [c_pin] + [self._joint(*pts[i + 1]) for i in range(len(pts) - 2)] + [c_bus]
        for n, (a, b) in enumerate(zip(pts, pts[1:])):
            self._wire(a, b, conns[n], conns[n + 1], net_node, label=(n == 0))

    @staticmethod
    def _path_clear(pts, all_boxes, part, end_part, pin_rects=()):
        segs = list(zip(pts, pts[1:]))
        for n, (a, b) in enumerate(segs):
            first, last = n == 0, n == len(segs) - 1
            rects = []
            for p2, r in all_boxes:
                if first and p2 is part:
                    # The start part is not a free pass: leaving a pin outward exits at
                    # once, but a leg that runs to the far side of the body crosses its
                    # core (an instrument wired through its own dial). Test an inset copy.
                    r = (r[0] + 8, r[1] + 8, r[2] - 8, r[3] - 8)
                    if r[0] >= r[2] or r[1] >= r[3]:
                        continue
                elif last and p2 is end_part:
                    continue
                rects.append(r)
            rects = rects + list(pin_rects)
            x0, x1 = sorted((a[0], b[0]))
            y0, y1 = sorted((a[1], b[1]))
            for (bx0, by0, bx1, by1) in rects:
                if x1 <= bx0 or x0 >= bx1 or y1 <= by0 or y0 >= by1:
                    continue
                return False
        return True

    def connect_net(self, net_name, pins, bus=None, rail=None, lane_reach=None):
        """Wire a net, optionally along a straight bus with junction objects.

        bus=("h", y)  horizontal run, one junction per distinct pin x, vertical spurs
        bus=("v", x)  vertical run,   one junction per distinct pin y, horizontal spurs
        rail=y        sugar for bus=("h", y)
        bus=None      star of 2-pin wires around the pin nearest the centroid

        Real Multisim files draw supply rails and shared nodes this way (HW122 has 223
        junction objects). It also avoids piling collinear wires of one net on top of
        each other, which is what a naive star does with 3+ pins on the same row.
        """
        assert len(pins) >= 2, pins
        node = self._net(net_name, [p.pin_port(pin) for p, pin in pins])

        def pos(item):
            return item[0].pin_pos(item[1])

        if bus is None and rail is not None:
            bus = ("h", rail)

        if bus is None:
            cx = sum(pos(p)[0] for p in pins) / len(pins)
            cy = sum(pos(p)[1] for p in pins) / len(pins)
            hub = min(pins, key=lambda p: (pos(p)[0] - cx) ** 2 + (pos(p)[1] - cy) ** 2)
            hub_pos = pos(hub)
            spokes = sorted((p for p in pins if p is not hub),
                            key=lambda p: abs(pos(p)[0] - hub_pos[0])
                            + abs(pos(p)[1] - hub_pos[1]))
            all_parts = self.obstacles()

            # The hub must NOT sit on the hub pin: a pin only connects when a wire
            # references its ConnectList id, and a zero-length wire is not a wire. Put the
            # junction just outside the hub part and draw that short stub, otherwise the
            # hub pin (and with it the whole net) is left floating - "Singular matrix".
            hub_j = self._stub_point(hub[0], hub_pos, all_parts, dist=24)
            if abs(hub_j[0] - hub_pos[0]) < 1 and abs(hub_j[1] - hub_pos[1]) < 1:
                hub_j = (hub_pos[0] + 24, hub_pos[1])

            # Three or more spokes around one hub overlap each other as soon as two of
            # them share a column: they then draw down the same stretch of wire. A bus
            # through the hub is the same drawing, and the bus code knows how to chain
            # pins that share a column, so let it do the work.
            if len(pins) > 2:
                xs = [pos(p)[0] for p in pins]
                ys = [pos(p)[1] for p in pins]
                if max(ys) - min(ys) >= max(xs) - min(xs):
                    bus, coord0 = "h", hub_j[1]
                else:
                    bus, coord0 = "v", hub_j[0]
                return self.connect_net(net_name, pins, bus=(bus, coord0), rail=None,
                                        lane_reach=48)

            if len(spokes) >= 2:           # three wires meet: a junction object
                stubs = [self._id() for _ in range(len(spokes) + 1)]
                self._junction(hub_j[0], hub_j[1], stubs, node)
            else:                          # two wires meet: one shared corner object
                corner = self._id()
                stubs = [corner, corner]
                self._placeholder(corner, hub_j[0], hub_j[1])
            # the hub stub is a wire like any other: it may not sit on a wire already
            # drawn (a star hub placed on a bus would double that bus segment)
            if not self._wire_clear(hub_pos, hub_j, node.get("CiID")):
                hub_j = self._free_hub(hub_pos, hub_j, all_parts, node.get("CiID"))
            self._wire(hub_pos, hub_j, hub[0].pin_conn(hub[1]), stubs[0], node)
            for i, (part, pin) in enumerate(spokes):
                self._elbow(part.pin_pos(pin), hub_j, all_parts, node,
                            part.pin_conn(pin), stubs[i + 1], part=part, end_part=hub[0])
            return node

        axis, coord = bus
        all_parts = self.obstacles()                 # [(part, rect)] for the whole sheet
        rects = [r for _, r in all_parts]
        lo = min((pos(p)[0] if axis == "h" else pos(p)[1]) for p in pins)
        hi = max((pos(p)[0] if axis == "h" else pos(p)[1]) for p in pins)
        lane_kw = {} if lane_reach is None else {"reach": lane_reach}
        coord = self._free_lane(axis, coord, (lo, hi), rects,
                                pins=[(part, pos((part, pin))) for part, pin in pins],
                                net_node=node, **lane_kw)
        if axis == "h":
            def key(p):
                return int(round(pos(p)[0]))

            def jpoint(k):
                return (k, coord)
        else:
            def key(p):
                return int(round(pos(p)[1]))

            def jpoint(k):
                return (coord, k)

        self._routing_pins = [pos((part, pin)) for part, pin in pins]
        groups, trunk_of = {}, {}
        for p in pins:
            groups.setdefault(key(p), []).append(p)

        # On a horizontal bus two pins a few units apart are the same column and should
        # share one trunk. On a vertical bus they are on different rows: give each its own
        # junction, otherwise their leads funnel down the bus column on top of each other.
        if axis == "h":
            snapped, anchor = {}, None
            for k in sorted(groups):
                if anchor is None or abs(k - anchor) > 32:
                    anchor = k
                snapped.setdefault(anchor, []).extend(groups[k])
            groups = snapped

        # Pins stacked in one column cannot each drop straight down: the lower pins sit
        # inside the bodies of the parts below, so every spur ends up in the same free
        # channel and the wires lie on top of each other (a "doubled" rail). Such a group
        # gets ONE shared trunk in a free adjacent column, with a tap per pin.
        lead = {}
        for k, ps in list(groups.items()):
            # Pins that share a column (horizontal bus) or a row (vertical bus) would all
            # spur along that same line, so the second spur is drawn on top of the first.
            # One shared trunk with a tap per pin fixes both orientations.
            if len(ps) < 2:
                continue
            ys = [pos(p)[1] if axis == "h" else pos(p)[0] for p in ps]
            # a trunk must approach the bus from one side only: taps on both sides make
            # it run through the bus and double back over its own segment
            if not (all(v < coord for v in ys) or all(v > coord for v in ys)):
                continue
            xc = self._free_column(axis, k, ys, coord, all_parts)
            if xc is None:
                continue
            moved = [p for p in ps
                     if self._lead_clear(pos(p), axis, xc, all_parts, p[0])]
            if len(moved) < 2:
                continue
            for p in moved:
                pt = pos(p)
                lead[p] = (xc, pt[1]) if axis == "h" else (pt[0], xc)
            groups.pop(k)
            if [p for p in ps if p not in moved]:
                groups[k] = [p for p in ps if p not in moved]
            groups.setdefault(xc, []).extend(moved)
            trunk_of[xc] = moved

        keys = sorted(groups)
        junc, left, right, spurs = {}, {}, {}, {}
        axis_pos = (lambda p: pos(p)[1]) if axis == "h" else (lambda p: pos(p)[0])
        for i, k in enumerate(keys):
            # a trunk group hands one wire to the bus; every other group needs one stub
            # per pin, or the pins that do not get the single stub are left unwired
            taps = 1 if k in trunk_of else len(groups[k])
            need = taps + (1 if i > 0 else 0) + (1 if i < len(keys) - 1 else 0)
            # a junction object is a drawn dot: only a real T earns one. A 2-end point is
            # a corner: both of its wires must reference the SAME object, because the
            # editor joins wires by shared ids, never by position (two ids at one point
            # leave both wires dangling - the Q2 ground and supply islands).
            if need == 2:
                corner = self._id()
                ids = [corner, corner]
                self._placeholder(corner, *jpoint(k))
            else:
                ids = [self._id() for _ in range(need)]
                if need >= 3:
                    self._junction(*jpoint(k), ids, node)
            c = 0
            if i > 0:
                left[k] = ids[c]
                c += 1
            if i < len(keys) - 1:
                right[k] = ids[c]
                c += 1
            spurs[k] = ids[c:]

        for ka, kb in zip(keys, keys[1:]):
            self._wire(jpoint(ka), jpoint(kb), right[ka], left[kb], node)

        # trunks first: an elbow that runs before them cannot see their wires and will
        # happily route down the same column
        for k in keys:
            if k in trunk_of:
                ps = sorted(groups[k], key=lambda p: -abs(axis_pos(p) - coord))
                self._trunk(ps, lead, jpoint(k), spurs[k], axis, node, all_parts)
        for k in keys:
            if k in trunk_of:
                continue
            ps = sorted(groups[k], key=lambda p: -abs(axis_pos(p) - coord))
            if axis == "v" and len(ps) > 1 and self._chain(ps, jpoint(k), spurs[k], node,
                                                           all_parts):
                continue        # pins on one row: chained, no lead drawn twice
            for n, (part, pin) in enumerate(ps):
                self._spur(part, pin, jpoint(k), spurs[k][n], axis, node, all_parts)
        return node

    def _chain(self, ps, jp, stubs, node, all_parts):
        """Chain pins that sit on the bus's own row: junction <- nearest <- ... <- far.

        Every lead of a vertical bus runs along the pin's row, so two pins on the same row
        would draw the same stretch twice. Chaining them end to end makes each stretch
        appear once, and the nearer pin is a connection point either way. False if the row
        between two of them is blocked, so the caller can fall back to plain spurs.
        """
        order = sorted(ps, key=lambda p: abs(part_x(p) - jp[0]))
        pts = [p[0].pin_pos(p[1]) for p in order]
        for a, b in zip(pts, pts[1:]):
            if abs(a[1] - b[1]) > 1:
                return False
            # a stretch of this row that is already drawn (a previous lead, a trunk) may
            # not be drawn again: the pins are all on the bus row, so it is one wire
            if not self._wire_clear(a, b, node.get("CiID")):
                return False
        prev, prev_conn = jp, stubs[0]
        for n, ((part, pin), here) in enumerate(zip(order, pts)):
            conn = stubs[n + 1] if n + 1 < len(stubs) else self._joint(here[0], here[1])
            if not self._path_clear([here, prev], all_parts,
                                    part if n else None, order[n - 1][0] if n else None,
                                    self.pin_boxes(skip_pts=(here, prev))):
                return False
            prev, prev_conn = here, conn
        prev, prev_conn = jp, stubs[0]
        for n, ((part, pin), here) in enumerate(zip(order, pts)):
            conn = stubs[n + 1] if n + 1 < len(stubs) else prev_conn
            self._wire(here, prev, part.pin_conn(pin), prev_conn, node, label=(n == 0))
            self._claim((int(round(here[0])), int(round(here[1]))), node)
            prev, prev_conn = here, conn
        return True

    def _spur(self, part, pin, jp, stub, axis, node, all_parts):
        """One pin's lead to its bus junction: straight when legal, elbow otherwise.

        Two rules for the straight run. It must meet the bus square on: a spur that
        arrives collinear with the bus is drawn on top of the rail segment between two
        junctions, which is the doubled-rail look. And it must not graze another pin:
        the bus may sit on a pin's row, the spur may not.
        """
        here = part.pin_pos(pin)
        square = (abs(here[0] - jp[0]) < 1) if axis == "h" else (abs(here[1] - jp[1]) < 1)
        if square and self._wire_clear(here, jp, node.get("CiID")) and                 self._path_clear([here, jp], all_parts, part, None,
                                 self.pin_boxes(skip_pts=(here, jp))):
            if getattr(part, "instrument", False):
                # an instrument's leads must never cross each other, so remember every
                # lead it has - including the straight ones drawn here
                self._meter_segs.setdefault(id(part), []).append((here, jp))
            self._wire(here, jp, part.pin_conn(pin), stub, node)
        else:
            self._elbow(here, jp, all_parts, node, part.pin_conn(pin), stub,
                        part=part, bus_axis=axis)

    def _node_text(self, at, wire_id):
        """Net-name label cloned from the donor, linked back to its wire."""
        nt = copy.deepcopy(self.label_proto)
        nt.set("ID", self._id())
        el = nt[0]
        el.set("Output", "")
        if el.get("Transformer-M20") is not None:
            el.set("Transformer-M20", str(int(at[0]) + 20))
            el.set("Transformer-M21", str(int(at[1]) + 20))
        links = el.find("Links")
        if links is None:
            links = ET.SubElement(el, "Links")
        for it in list(links):
            links.remove(it)
        it = ET.SubElement(links, "Item")
        it.set("ID", wire_id)
        it.set("Class", "CIITLinkComp")
        self.comp_objects.append(nt)
        return nt

    def _nodetext_proto(self):
        if getattr(self, "_nt_proto", None) is None:
            self._nt_proto = ET.Element("CODNodeTextComp", {
                "Class": "CODNodeTextComp", "instID": "0", "Stretchable": "0",
                "Moveable": "1", "LabelSelectable": "1", "Selectable": "1",
                "LockedPenColor": "0", "LockedBrushColor": "0", "Layer": "511",
                "Output": "", "PenColor": "255", "FgColor": "0", "BgColor": "16777215",
                "Font-Height": "-13", "Font-Width": "0", "Font-Escapement": "0",
                "Font-Orientation": "0", "Font-Weight": "700", "Font-Italic": "0",
                "Font-Underline": "0", "Font-StrikeOut": "0", "Font-CharSet": "0",
                "Font-OutPrecision": "3", "Font-ClipPrecision": "2", "Font-Quality": "1",
                "Font-PitchAndFamily": "34", "Font-FaceName": "&ASCArial",
                "Transformer-M00": "1", "Transformer-M01": "0", "Transformer-M10": "0",
                "Transformer-M11": "1", "Transformer-M20": "0", "Transformer-M21": "0",
                "Hidden": "0",
            })
        return self._nt_proto

    def _node_attrs_template(self):
        """A real CiNode Attributes block to clone (a GUI-saved file always has 33 groups).

        An EMPTY <Attributes/> is what made every generated net unreferenceable: the
        simulator reads the ground flag from group 16, so with no groups nothing anchored
        the matrix and the run died with `Singular matrix ... floating with respect to
        net 0` while the netlist itself checked out clean.
        """
        for src in (self.elements, next(self.root.iter("Elements"), None)):
            if src is None:
                continue
            for it in src:
                if it.get("Class") == "CiNode":
                    a = it[0].find("Attributes")
                    if a is not None and len(list(a)):
                        return copy.deepcopy(a)
        return None

    def _net(self, name, ports):
        key = name or ("N%03d" % (len([e for e in self.elements if e.get("Class") == "CiNode"]) + 1))
        enc = key if key.startswith("&") else "&ASC" + key
        for it in self.elements:
            if it.get("Class") == "CiNode" and it[0].get("LocalName") == enc:
                node = it
                break
        else:
            node = ET.SubElement(self.elements, "Item")
            node.set("CiID", self._id())
            node.set("Class", "CiNode")
            n = ET.SubElement(node, "CiNode")
            n.set("Class", "CiNode")
            n.set("LocalName", enc)
            n.set("Circuit", self.circuit.get("CiID") or "")
            n.append(self._node_attrs(key))
            n.append(ET.Element("Ports"))
            self.circuit.find("Nodes").append(_ref(node.get("CiID")))
        for p in ports:
            if p:
                n = node[0].find("Ports")
                if not any(i.get("CiID") == p for i in n):
                    it = ET.SubElement(n, "Item")
                    it.set("CiID", p)
        return node

    def _node_attrs(self, key):
        """Attributes block for a net: 33 groups cloned from a real file.

        Group 16 is the reference/ground flag. It carries one CiaDOUBLE on the net named
        `0` and is empty on every signal net, exactly as the GUI writes it.
        """
        attrs = (copy.deepcopy(self.node_attrs_proto)
                 if self.node_attrs_proto is not None else ET.Element("Attributes"))
        groups = list(attrs)
        if len(groups) > 16:
            g = groups[16]
            for c in list(g):
                g.remove(c)
            if key == "0":
                it = ET.SubElement(g, "Item")
                it.set("Class", "CiaDOUBLE")
        return attrs

    def _rebuild_instance_registry(self):
        """Rebuild the per-part registry the application keeps beside the schematic.

        A GUI-saved project carries one `RefDesGUIDsForSave` entry per placed part and one
        `CSCH_CAPVirtualComponentPin` per pin, the latter storing the pin's net (`lastnet`).
        A generator that starts from a template inherits the template's single entry, so none
        of the real parts is registered: the sheet simulates, and an instrument - which is
        resolved through this table - never reports a value (`0 V` on every range).
        """
        mgr = next(self.root.iter("RefDesMgr"), None)
        if mgr is None:
            return
        guids = next(self.root.iter("RefDesGUIDsForSave"), None)   # under CCompInstancePropManager
        pins = mgr.find("ComponentPins")
        pin_tpl = guid_tpl = None
        if pins is not None:
            for item in pins.iter("Item"):
                if item.find("Items") is not None and len(item.find("Items")):
                    pin_tpl = copy.deepcopy(item)
                    break
        if guids is not None:
            for item in guids.iter("Item"):
                if item.get("CiCompGUID"):
                    guid_tpl = item
                    break
        if guid_tpl is None or pin_tpl is None:
            return

        net_of_port = {}
        for it in self.elements:
            if it.get("Class") == "CiNode":
                for ref in it[0].find("Ports"):
                    net_of_port[ref.get("CiID")] = (it[0].get("LocalName") or "")
        port_name = {}
        for it in self.elements:
            if it.get("Class") == "CiPort":
                port_name[it.get("CiID")] = (it[0].get("LocalName") or "")

        for lst in (guids, pins):
            for child in list(lst):
                lst.remove(child)

        # per-refdes records: the application stores each part's SPICE template here, so a
        # file carrying only the template's leftover entry has no template for its own parts.
        # Shape: RefDesInfoContainer > CIRToInfoMap > CIRToInfoMapItem(CIRKey) > RefDesInfo
        containers = mgr.find("RefDesInfoContainers")
        map_el = next((m for m in self.root.iter("CIRToInfoMap")), None)
        info_tpl = next((i for i in self.root.iter("RefDesInfo")), None)
        if map_el is not None and info_tpl is not None:
            for child in list(map_el):
                map_el.remove(child)
            for part in self.parts:
                comp = part.comp
                ref = (comp.get("LocalName") or "").replace("&ASC", "")
                if not ref:
                    continue
                prefix = re.match(r"[A-Za-z]+", ref)
                prefix = prefix.group(0) if prefix else ref
                info = copy.deepcopy(info_tpl)
                info.set("IRPrefix", "&ASC" + prefix)
                info.set("IRNumber", ref[len(prefix):] or "1")
                data = info.find("RefDesInfoData")
                if data is not None:
                    old = (data.get("RefDes") or "").replace("&ASC", "")
                    bits = old.split("!")
                    if len(bits) > 3:
                        bits[3] = ref
                        data.set("RefDes", "&ASC" + "!".join(bits))
                    data.set("Prefix", "&ASC" + prefix)
                    data.set("Number", ref[len(prefix):] or "1")
                # The record also carries the part's INSTANCE TEMPLATE and its pin order.
                # Cloning the template project's (an amplifier: "a%p_a ... 1A 1Y") gives
                # every part someone else's element line, which is how a sheet ends up
                # simulating garbage while the schematic looks perfect.
                tpl = ""
                for grp in list(comp.find("Attributes"))[1:2]:
                    for g in grp:
                        if g.tag in ("CiaSpiceTmpltExprt", "CiaCString"):
                            tpl = g.get("String") or ""
                if tpl:
                    info.set("SpiceTemplate", tpl)
                else:
                    info.attrib.pop("SpiceTemplate", None)
                holder = next((it.get("CiID") for it in self.elements
                               if len(it) and it[0] is comp), None)
                pin_names = [(it[0].get("LocalName") or "").replace("&ASC", "")
                             for it in self.elements
                             if it.get("Class") == "CiPort"
                             and it[0].get("Component") == holder]
                for tag in ("PinOrderCIR", "PinOrderIR", "PinNumbersCIR", "PinNumbersIR"):
                    box = info.find(tag)
                    if box is None:
                        continue
                    for child in list(box):
                        box.remove(child)
                    for i, pin in enumerate(pin_names, 1):
                        e = ET.SubElement(box, tag[:-3] + "Item")
                        attr = ("PinNameCIR" if tag.endswith("CIR") else "PinNameIR")                             if tag.startswith("PinOrder") else                             ("PinNumberCIR" if tag.endswith("CIR") else "PinNumberIR")
                        e.set(attr, "&ASC" + (pin if tag.startswith("PinOrder") else str(i)))
                item = ET.SubElement(map_el, "CIRToInfoMapItem")
                item.set("CIRKey", "&ASC" + ref)
                item.append(info)

        for part in self.parts:
            comp = part.comp
            inst = comp.get("InstanceID")
            if not inst:
                continue
            g = copy.deepcopy(guid_tpl)
            g.set("CiCompGUID", "&ASC" + inst)
            g.set("InstanceGUID", "{%s}" % str(uuid.uuid4()).upper())
            guids.append(g)

            holder = copy.deepcopy(pin_tpl)
            items = holder.find("Items")
            for child in list(items):
                items.remove(child)
            for ref in comp.find("Ports"):
                pid = ref.get("CiID")
                e = ET.SubElement(items, "CSCH_CAPVirtualComponentPin")
                e.set("Class", "CSCH_CAPVirtualComponentPin")
                e.set("GUID", inst)
                e.set("PinName", port_name.get(pid, ""))
                net = net_of_port.get(pid, "")
                e.set("lastnet", net)
            pins.append(holder)

    def _rebuild_net_labels(self):
        """One `CSchDesignNetLabel` record per net, naming that net.

        The design net container is how the application tracks a net's name; an empty one
        leaves names unresolved, which also strands an instrument that resolves its probed
        node by name. Rebuild it from the sheet's own nets, keeping the container shape the
        template wrote.
        """
        for cont in self.root.iter("CDesignNetContainer"):
            for nl in cont:
                if nl.tag != "NetLabels":
                    continue
                holder = None
                for item in list(nl):
                    for cand in list(item):
                        if cand.tag == "Items":
                            holder = cand
                            break
                    if holder is not None:
                        break
                if holder is None:
                    continue
                for rec in list(holder):
                    holder.remove(rec)
                for it in self.elements:
                    if it.get("Class") != "CiNode":
                        continue
                    rec = ET.SubElement(holder, "CSchDesignNetLabel")
                    rec.set("Class", "CSchDesignNetLabel")
                    rec.set("Modifier", "256")
                    rec.set("Value", "")
                    rec.set("ID", "{%s}" % str(uuid.uuid4()).upper())
                    rec.set("LastLocalName", "")
                    rec.set("LastOverruleName", "")
                    rec.set("LastNetName", it[0].get("LocalName") or "")
                    rec.set("Priority", "0")
                return

    def _rebuild_node_refs(self):
        """CiPort.Nodes must list the CiNode each port belongs to."""
        net_of = {}
        for it in self.elements:
            if it.get("Class") != "CiNode":
                continue
            for ref in it[0].find("Ports"):
                net_of[ref.get("CiID")] = it.get("CiID")
        for it in self.elements:
            if it.get("Class") != "CiPort":
                continue
            nodes = it[0].find("Nodes")
            if nodes is None:
                nodes = ET.SubElement(it[0], "Nodes")
            for r in list(nodes):
                nodes.remove(r)
            ci = net_of.get(it.get("CiID"))
            if ci:
                r = ET.SubElement(nodes, "Item")
                r.set("CiID", ci)

    def netlist(self):
        """{net_name: ["R1.1", "Q2.B", ...]} from the CiNode port back-references."""
        net_of_port = {}
        for it in self.elements:
            if it.get("Class") != "CiNode":
                continue
            name = it[0].get("LocalName")
            for ref in it[0].find("Ports"):
                net_of_port[ref.get("CiID")] = name
        out = {}
        for p in self.parts:
            for pin, info in p.pins().items():
                net = net_of_port.get(info["port"]) or net_of_port.get(info["conn"])
                out.setdefault(net or "<unconnected>", []).append("%s.%s" % (p.name, pin))
        return out

    def model_element(self, comp):
        """The CiModel element this component points at (the part's composition)."""
        mid = comp.get("Model")
        for it in self.elements:
            if it.get("Class") == "CiModel" and it.get("CiID") == mid:
                return it
        return None

    @staticmethod
    def meter_parts(palette, mode):
        """Return (geometry_source, model_source) for a meter of the requested mode.

        A donor project can hold several multimeter *parts* that differ in two independent
        ways:
          * the symbol - some are authored around the symbol origin, others carry a large
            baked-in child offset (e.g. every child translated by +597/+279), so placing
            them at (x, y) draws them hundreds of units away;
          * the model - `R_multi_meter 1e-5` is an ammeter (a short), `1e9` is a voltmeter.
        So geometry and model are chosen separately: clone the origin-local symbol, then
        attach the model that matches the requested quantity.
        """
        want_volts = (mode == 1)
        geo = mdl = None
        for name in palette.refdes_list():
            db, prefix = palette.part_of(palette.components[name])
            if prefix != "XMM":
                continue
            item = palette.components[name]
            sid = item[0].get("SymCompID")
            sym = palette.symbol_index.get(sid)
            if sym is not None and geo is None:
                offs = [(float(e.get("Transformer-M20") or 0), float(e.get("Transformer-M21") or 0))
                        for e in sym[0].iter() if e is not sym[0] and e.get("Transformer-M20")]
                if not offs or max(abs(a) for a, _ in offs) < 50:
                    geo = name
            card = ""
            for it in palette.elements:
                if it.get("Class") == "CiModel" and it.get("CiID") == item[0].get("Model"):
                    for grp in list(it[0].find("Attributes"))[1:2]:
                        for g in grp:
                            if g.tag in ("CiaSpiceTmpltExprt", "CiaCString"):
                                card = g.get("String") or ""
            m = re.search(r"R_multi_meter\s+\S+\s+\S+\s+([0-9.eE+-]+)", card)
            if m and ((float(m.group(1)) >= 1e6) == want_volts) and mdl is None:
                mdl = name
        geo = geo or palette.pick_refdes("XMM")
        return geo, (mdl or geo)

    def _borrow_model(self, part, palette, from_refdes, tag, name=None):
        """Copy another palette part's CiModel onto `part`, with a unique subckt name."""
        src = palette.components[from_refdes][0]
        for it in palette.elements:
            if it.get("Class") != "CiModel" or it.get("CiID") != src.get("Model"):
                continue
            mit = copy.deepcopy(it)
            self._remap(mit, {})
            name = name or ("%s_%s" % (part.name, tag))
            mit.set("LocalName", "&ASC" + name)
            if len(mit):
                mit[0].set("LocalName", "&ASC" + name)   # the name the netlister expands
            for grp in list(mit[0].find("Attributes"))[1:2]:
                for g in grp:
                    if g.tag in ("CiaSpiceTmpltExprt", "CiaCString"):
                        txt = g.get("String") or ""
                        g.set("String", re.sub(r"(\.subckt\s+)\S+", r"\g<1>" + name, txt))
            self.elements.append(mit)
            part.comp.set("Model", mit.get("CiID"))
            models = self.circuit.find("Models")
            refs = [r.get("CiID") for r in models]
            if mit.get("CiID") not in refs:
                r = ET.SubElement(models, "Item")
                r.set("CiID", mit.get("CiID"))
            return True
        return False

    def add_instrument(self, palette, refdes, x, y, proto="XMM", mode=0, signal=1):
        """Place a multimeter and give it the InstrumentProperties Multisim expects.

        An instrument is not just a symbol: it needs a CSourceSymbolCollectNode in
        CIITHierDoc/InstrumentsData carrying the measurement mode. Without it the meter
        draws but reads nothing.
        """
        if proto == "XMM":
            geo, mdl = self.meter_parts(palette, mode)
            part = self.add_part(palette, geo, x, y, refdes)
            # EVERY instrument gets its own model, named `X<refdes>_<doc number>`: a
            # GUI-saved project never shares one meter model between two meters, and the
            # name is what marks the subckt as an instrument rather than an ordinary call.
            self._borrow_model(part, palette, mdl, "V" if mode == 1 else "A",
                               name="X%s_%s" % (refdes, self.circuit_id))
        else:
            part = self.add_part(palette, palette.pick_refdes(proto), x, y, refdes)
        part.instrument = True          # a meter pin is never a bus-lane landmark (see connect_net)

        src = None
        for name, node in self._inst_proto.items():
            if name.startswith(proto):
                src = node
                break
        if src is None:
            return part
        node = copy.deepcopy(src)
        node.set("CompLongName", "&ASC" + refdes + "#1/" + self.sheet_name + ":")
        for el in node.iter("Element"):
            key = (el.get("Key") or "").replace("&ASC", "")
            if key == "NI_EWB_MEASUREMENT_MODE":
                el[0].set("Data", str(mode))
            elif key == "NI_EWB_SIGNAL_MODE":
                el[0].set("Data", str(signal))
            elif key == "NI_EWB_CURRENTDISPLAYDATA_VALUE":
                # the GUI stores a formatted reading with its unit ("4.611 V"), never a bare 0
                el[0].set("Data", "&ASC0 %s" % ("V" if mode == 1 else "A"))
        self.inst_data.append(node)
        return part

    # ------------------------------------------------------------ checks ----
    def page_rect(self):
        """The printable page border, in the same 1/1000 inch units as symbols."""
        best = None
        for it in self.root.iter("CODRectComp"):
            e = it[0] if len(it) else it
            if e.get("pt0X") is None:
                continue
            r = (int(e.get("pt0X")), int(e.get("pt0Y")),
                 int(e.get("pt1X")), int(e.get("pt1Y")))
            if best is None or (r[2] - r[0]) * (r[3] - r[1]) > (best[2] - best[0]) * (best[3] - best[1]):
                best = r
        if best is not None:
            return best
        return (0, 0, 960, 720)

    def validate(self, margin=10):
        """Return a list of human-readable problems: off-page parts, floating nets, loose pins."""
        problems = []
        x0, y0, x1, y1 = self.page_rect()

        net_ports = {}
        for it in self.elements:
            if it.get("Class") != "CiNode":
                continue
            net_ports[it[0].get("LocalName", "")] = [
                r.get("CiID") for r in it[0].find("Ports")]

        for name, ports in net_ports.items():
            if len(ports) < 2:
                problems.append("floating net %r has %d pin(s)" % (name, len(ports)))

        used = {p for ports in net_ports.values() for p in ports}
        for it in self.elements:
            if it.get("Class") != "CiPort":
                continue
            if it.get("CiID") not in used:
                problems.append("pin %r of %s is on no net"
                                % (it[0].get("LocalName", ""), self._owner_name(it)))

        for part in self.parts:
            for pin, info in part.pins().items():
                px, py = info["pos"]
                if not (x0 + margin <= px <= x1 - margin and y0 + margin <= py <= y1 - margin):
                    problems.append("part %s pin %s at (%d,%d) is outside page %s"
                                    % (part.name, pin, px, py, (x0, y0, x1, y1)))
                    break
        return problems

    def _owner_name(self, port_item):
        cid = port_item.get("CiID")
        for it in self.elements:
            if it.get("Class") != "CiComponent":
                continue
            for ref in it[0].find("Ports"):
                if ref.get("CiID") == cid:
                    return it[0].get("LocalName", "?")
        return "?"

    def set_view(self, zoom_index=8, offset_x=0, offset_y=0):
        for vs in self.root.iter("IITViewState"):
            vs.set("ZoomIndex", str(zoom_index))
            vs.set("OffsetX", str(offset_x))
            vs.set("OffsetY", str(offset_y))

    # --------------------------------------------------------------- save ----
    def xml(self):
        return _serialize(self.root)

    def _prune_stubs(self):
        """Drop junction stubs (and their placeholder objects) that no wire uses.

        Every stub is a pin as far as the netlister is concerned; one that nothing
        attaches to becomes a floating node, which shows up as
        "Singular matrix ... Check node N. Ensure it is not floating with respect to
        net 0 (ground)" and cancels the simulation.
        """
        used = set()
        for e in self.comp_objects:
            if e.get("Class") == "CIITLinkComp":
                used.add(e[0].get("Connect1"))
                used.add(e[0].get("Connect2"))
        dead = set()
        for e in self.comp_objects:
            if e.get("Class") != "CODPinComp":
                continue
            cl = e[0].find("ConnectList")
            if cl is None:
                continue
            for it in list(cl):
                if it.get("ID") not in used:
                    dead.add(it.get("ID"))
                    cl.remove(it)
        for gone in list(self.comp_objects):
            if gone.get("Class") == "CODPinComp" and gone[0].find("ConnectList") is None:
                self.comp_objects.remove(gone)
        for r in list(self.ref_objects):
            if r.get("ID") in dead:
                self.ref_objects.remove(r)
        return len(dead)

    def set_sheet_name(self, name=None):
        """Re-derive every instrument key from the SHEET name the document already carries.

        Do NOT rename the sheet: the same name is repeated in `CProject/@Name`,
        `Sheet/@SheetName`, `RefDesInfoContainer/@CIR` and every `RefDesInfoData/@RefDes`
        path. Renaming only `DesignSheet/@Title` leaves the document self-inconsistent and
        Multisim crashes just opening it. The key is what has to move, not the sheet.
        """
        for node in self.inst_data:
            ref = (node.get("CompLongName") or "").replace("&ASC", "")
            base = ref.split("#", 1)[0]
            node.set("CompLongName", "&ASC" + base + "#1/" + self.sheet_name + ":")

    def save(self, path):
        import ms14
        # ports are wired after add_part(), so the port->node back-references must be
        # rebuilt from the final netlist, not from the placement-time state
        self._rebuild_node_refs()
        self._prune_stubs()
        self._prune_models()
        self._dedupe_models()
        self.set_sheet_name()
        self._rebuild_ref_classes()
        self._rebuild_instance_registry()
        self._rebuild_net_labels()
        self._sync_circuit_refs()
        self._stamp_circuit()
        xml = self.xml()
        # The sheet name is the document's identity and it is repeated in six places
        # (CProject/@Name, Sheet/@SheetName, DesignSheet/@Title, RefDesInfoContainer/@CIR,
        # every RefDesInfoData/@RefDes path, and the instrument keys). Rename it in ONE of
        # them and Multisim crashes on open; leave it as the skeleton's name and the meter
        # keys can never match, so every meter reads 0 V. Rename every occurrence at once,
        # to the output file stem - which is exactly what a GUI-saved project has.
        import os
        stem = os.path.splitext(os.path.basename(str(path)))[0]
        if stem:
            for old_name in {self.sheet_name, "Skeleton", "TestOnlyInventor"}:
                if old_name and old_name != stem:
                    xml = xml.replace(old_name, stem)
            self.sheet_name = stem
        ms14.pack(xml, path)


def _flatten_card(spice):
    """Collapse a multi-line SPICE card to one statement line.

    Drops comment lines and joins '+'-continuations, so the stored card is exactly what
    the solver reads: ".MODEL <name> npn IS=... BF=...". A card whose first lines are
    '*' comments can be read as all-comment, and the device then has no model at all -
    its internal nodes float, which is "Singular matrix. Check node N".
    """
    text = (spice or "").replace("\r\n", "\n")
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        if line.startswith("+"):
            if out:
                out[-1] += " " + line[1:].strip()
            continue
        out.append(line)
    card = " ".join(out)
    # A card that was written with a continuation marker *inside* one line ("... NSUB=1e15
    # + RD=1 ...") still carries a lone '+' token. SPICE reads that as a parameter name
    # and rejects the whole card, which costs the device its model. Only a '+' with space
    # on both sides is that marker - "1e+5" stays.
    return re.sub(r"(?<=\s)\+(?=\s)", " ", card).replace("  ", " ").strip()


def _ref(ciid):
    it = ET.Element("Item")
    it.set("CiID", ciid)
    return it


def _model_card(model_item):
    """The SPICE text of a CiModel - what makes two models the same model."""
    for it in model_item.iter("CiaCString"):
        return (it.get("String") or "").replace("&ASC", "")
    return ""


def _part_value(comp):
    attrs = comp.find("Attributes")
    try:
        return attrs[2][0].find("parameters")[1].get("Value") or ""
    except Exception:
        return ""


def part_x(pin):
    return pin[0].pin_pos(pin[1])[0]


def _seg_overlaps(a, b, c, d, tol=2):
    """True if two collinear segments share more than a point of length."""
    if abs(a[1] - b[1]) <= tol and abs(c[1] - d[1]) <= tol:
        if abs(a[1] - c[1]) > tol:
            return False
        lo = max(min(a[0], b[0]), min(c[0], d[0]))
        hi = min(max(a[0], b[0]), max(c[0], d[0]))
        return hi - lo > tol
    if abs(a[0] - b[0]) <= tol and abs(c[0] - d[0]) <= tol:
        if abs(a[0] - c[0]) > tol:
            return False
        lo = max(min(a[1], b[1]), min(c[1], d[1]))
        hi = min(max(a[1], b[1]), max(c[1], d[1]))
        return hi - lo > tol
    return False


def _seg_hits(a, b, c, d, tol=2):
    """True if two axis-aligned segments cannot share space.

    Covers a proper crossing, a T (one endpoint inside the other - the editor turns that
    into a junction and the two nets merge) and a collinear overlap. Only segments of
    *different* nets are ever compared, so a bus and its own spurs stay safe.
    """
    ah = abs(a[1] - b[1]) <= tol
    ch = abs(c[1] - d[1]) <= tol
    if ah and ch:
        if abs(a[1] - c[1]) > tol:
            return False
        lo = max(min(a[0], b[0]), min(c[0], d[0]))
        hi = min(max(a[0], b[0]), max(c[0], d[0]))
        return hi > lo + tol
    if not ah and not ch:
        if abs(a[0] - c[0]) > tol:
            return False
        lo = max(min(a[1], b[1]), min(c[1], d[1]))
        hi = min(max(a[1], b[1]), max(c[1], d[1]))
        return hi > lo + tol
    h, v = ((a, b), (c, d)) if ah else ((c, d), (a, b))
    hx0, hx1 = sorted((h[0][0], h[1][0]))
    vy0, vy1 = sorted((v[0][1], v[1][1]))
    return (hx0 - tol <= v[0][0] <= hx1 + tol) and (vy0 - tol <= h[0][1] <= vy1 + tol)


def _seg_cross(a, b, c, d, tol=2):
    """True if axis-aligned segments a-b and c-d cross at an interior point."""
    ah = abs(a[1] - b[1]) < tol
    ch = abs(c[1] - d[1]) < tol
    if ah == ch:
        return False
    if not ah:
        a, b, c, d = c, d, a, b
        ah, ch = ch, ah
    # a-b horizontal, c-d vertical
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((c[1], d[1]))
    return (x0 + tol < c[0] < x1 - tol) and (y0 + tol < a[1] < y1 - tol)


def _serialize(root):
    ET.indent(root, space="")
    return '<?xml version="1.0" encoding="ASCII"?>\n' + ET.tostring(root, encoding="unicode")


class Part:
    def __init__(self, builder, comp, sym):
        self.b = builder
        self.comp = comp
        self.sym = sym
        # names are stored &ASC-prefixed; the plain text is what every check reports
        self.name = (comp.get("LocalName") or "").replace("&ASC", "")
        self.instrument = False
        self._pins = None

    def pins(self):
        if self._pins is None:
            x = float(self.sym[0].get("Transformer-M20") or 0)
            y = float(self.sym[0].get("Transformer-M21") or 0)
            pins = {}
            for pe in self.sym.iter("CIITPinSymbolComp"):
                for conn in pe.iter("CIITPinConnectorComp"):
                    cx = float(conn.get("ptCenterX") or 0)
                    cy = float(conn.get("ptCenterY") or 0)
                    cl = conn.find("ConnectList")
                    pid = cl[0].get("ID") if cl is not None and len(cl) else None
                    label = (pe.get("PinName") or "").replace("&ASC", "")
                    pins[label] = {
                        "conn": pid, "port": pe.get("PortID"),
                        "pos": (x + cx, y + cy), "number": (pe.get("PinNumber") or "").replace("&ASC", ""),
                    }
            self._pins = pins
        return self._pins

    def set_pin_note(self, pin, note):
        self.pins()[pin]["note"] = note

    def set_display_value(self, text):
        """Set the text drawn under the symbol (the part's visible value/name)."""
        for t in self.sym.iter("CIITSymTextCompValue"):
            t.set("Output", "&ASC" + str(text))
        return self

    def set_model_text(self, spice, name=None):
        """Replace this part's SPICE card (usually multisim_db.part(name)['spice']).

        Multisim keeps the model in CiModel/Attributes[1]/CiaCString@String, prefixed
        with &ASC. `name` rewrites the model LocalName ("&ASC<refdes>__<dbname>__1").
        """
        m = self.b.model_element(self.comp)
        if m is None:
            raise KeyError("part %s has no CiModel" % self.name)
        node = m[0] if len(m) and m[0].tag == "CiModel" else m   # Item/CiModel/Attributes
        txt = _flatten_card(spice)
        new = None
        if name:
            # The card must *declare* the name this CiModel carries. Two CiModels may not
            # declare the same .MODEL/.SUBCKT: Multisim then expands one definition per
            # component and the extra copies' internal nodes are left floating - that is
            # "Singular matrix. Check node N" at simulation time. Rename the declaration,
            # not just the element: a .MODEL card's own name is what the Q line calls.
            new = "%s__%s__1" % (self.name, name)
            txt = re.sub(r"(?im)^(\s*\.(?:model|subckt)\s+)\S+",
                         lambda mm: mm.group(1) + new, txt, count=1)
        txt = txt.replace("\n", "\r\n")
        at = node.find("Attributes")
        for it in at:
            for g in it:
                if g.tag == "CiaCString":
                    g.set("String", "&ASC" + txt)
        if new:
            for el in (m, node):
                el.set("LocalName", "&ASC" + new)
        # The component also keeps a *snapshot of the database row* it was placed from
        # (Attributes[4], strings[0..35]). That row names the donor's part and model
        # ("2N2222A" / "Q2N2222A") and carries its own copy of the card. Left alone after a
        # model swap it contradicts the CiModel; written with the CiModel's renamed card
        # it becomes a *second definition of the same model name* in the file. Multisim
        # then has more than one definition of that name and the copies' internal device
        # nodes are left floating - "Singular matrix. Check node N" at run time. Keep this
        # row internally consistent (db part name, db model name, db card text) and give
        # the card in it the database's own name, never the CiModel's.
        self.set_db_record(name, spice)
        return self

    def unique_db_row_card(self, refdes):
        """Give this part's database-row card a name of its own.

        Several parts sharing one row name is normal (twelve 2N3904s carry twelve identical
        rows). What must never happen is a row declaring the name the CiModel defines: that
        is a second definition of one model, and the extra copy's internal device nodes
        belong to no element ("Singular matrix. Check node N"). See checksim.py C11.
        """
        at = self.comp.find("Attributes")
        if at is None or len(at) < 5:
            return self
        coll = at[4].find("CiaCollString")
        row = [i for i in coll.iter("Item")] if coll is not None else []
        if len(row) < 6:
            return self
        txt = (row[5].get("Value") or "").replace("&ASC", "")
        if not txt.lstrip().upper().startswith((".MODEL", ".SUBCKT")):
            return self
        new = re.sub(r"(?im)^(\s*\.(?:model|subckt)\s+)\S+",
                     lambda m: m.group(1) + refdes, _flatten_card(txt), count=1)
        row[5].set("Value", "&ASC" + new)
        return self

    def set_db_record(self, db_name, db_spice):
        """Refresh the component's database-row strings from the part it now represents."""
        at = self.comp.find("Attributes")
        if at is None or len(at) < 5:
            return
        coll = at[4].find("CiaCollString")
        if coll is None:
            return
        coll = coll.find("strings")
        if coll is None or len(coll) < 6:
            return
        row = [i for i in coll.iter("Item")]
        if db_name:
            try:
                rec = multisim_db.part(db_name)
            except Exception:
                rec = {}
            if rec.get("name"):
                row[1].set("Value", "&ASC" + rec["name"])
            if rec.get("model"):
                row[3].set("Value", "&ASC" + rec["model"])
            for i, key in ((8, "manufacturer"), (9, "description")):
                if i < len(row) and rec.get(key):
                    row[i].set("Value", "&ASC" + str(rec[key]))
        if db_spice:
            # One clean statement under the database's own name - the donor stores exactly
            # that shape. The raw block opens with '*' comment lines and reads as
            # all-comment to a SPICE parser.
            row[5].set("Value", "&ASC" + _flatten_card(db_spice))

    def pin_names(self):
        return list(self.pins())

    def pin_pos(self, name):
        return self.pins()[name]["pos"]

    def pin_conn(self, name):
        return self.pins()[name]["conn"]

    def pin_port(self, name):
        return self.pins()[name]["port"]


if __name__ == "__main__":
    import sys

    palette = Palette("xml/Electronics1.xml")
    print("palette parts:")
    for k in palette.refdes_list():
        print("  ", k, palette.part_of(palette.components[k]))

    import ms14

    skel = open("xml/skeleton.xml", encoding="utf-8").read()
    b = Builder(skel)
    b.clear()
    r1 = b.add_part(palette, palette.pick("RESISTOR_VIRTUAL"), 200, 200, "R1", "10k")
    v1 = b.add_part(palette, palette.pick("DC_POWER"), 100, 200, "V1", "5V")
    g1 = b.add_part(palette, palette.pick("GROUND"), 100, 300, "0", None)
    print("R1 pins", r1.pins())
    print("V1 pins", v1.pins())
    print("GND pins", g1.pins())
    b.save("../../t1.ms14" if False else "build_t1.ms14")
    print("wrote build_t1.ms14")
