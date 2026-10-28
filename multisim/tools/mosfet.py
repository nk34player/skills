"""Synthesize a MOSFET part (2N7000 / NMOS or a PMOS) from the 2N2222A clone.

There is no MOSFET in any .ms14 on this machine, and Multisim's Automation API cannot
place parts (ReplaceComponent access-violates the COM server). So the part is built from
the pieces the file format already understands:

  * component skeleton, ports, pin objects, symbols  -> cloned from 2N2222A
  * pin order S, G, D                                -> MOS_3TEN pin list in the master DB
  * SPICE model                                      -> a real MOS level-1/3 card

The symbol is redrawn with the standard 3-terminal MOSFET glyph (gate bar, channel bar,
D/S taps, bulk arrow), which Multisim renders from CODLineComp/CODEllipseComp primitives.

Usage:
    from mosfet import mos_palette, NMOS_MODEL, PMOS_MODEL
    pal = mos_palette("xml/Electronics1.xml")          # Palette + MOSFET parts
    q = b.add_part(pal, "MOSFET_N", x, y, "M1")        # NMOS with S/G/D pins
"""

import copy
import re
import xml.etree.ElementTree as ET

import ms14build

# SPICE level-1 model cards. A MOSFET is used here as a switch, so level 1 is enough and
# keeps the DC operating point well behaved (no convergence games with level 3/49).
NMOS_MODEL = (
    ".MODEL M2N7000_NMOS NMOS LEVEL=1 VT0=2.1 KP=1.48E-1 GAMMA=1.0 PHI=0.7 "
    "LAMBDA=1.0E-2 TOX=1.0E-7 NSUB=1.0E15 RD=1 RS=1 PB=0.8 MJ=0.5 "
    "CJ=2.0E-4 CJSW=1.0E-9 CGSO=1.0E-9 CGDO=1.0E-9 CGBO=1.0E-9"
)
PMOS_MODEL = (
    ".MODEL MBS250_PMOS PMOS LEVEL=1 VT0=-2.0 KP=1.0E-1 GAMMA=0.6 PHI=0.7 "
    "LAMBDA=2.0E-2 TOX=1.0E-7 NSUB=1.0E15 RD=1 RS=1 PB=0.8 MJ=0.5 "
    "CJ=2.0E-4 CJSW=1.0E-9 CGSO=1.0E-9 CGDO=1.0E-9 CGBO=1.0E-9"
)

# MOS_3TEN / MOS_3TEP pin order in the master DB: S, G, D (numbers 3, 2, 1 on the BJT
# symbol map to E, B, C, so the E pin becomes S, B becomes G, C becomes D).
PIN_MAP = {"E": "S", "B": "G", "C": "D"}

# geometry in symbol coordinates (same 45..81 box the donors use)
GATE_X = 52
CHANNEL_X = 58
DRAIN_X = 63


def _glyph_nmos():
    """Standard n-channel enhancement MOSFET: gate bar, broken channel, bulk arrow."""
    return [
        # (kind, coords...)
        ("line", GATE_X, 51, GATE_X, 75),          # gate bar
        ("line", CHANNEL_X, 51, CHANNEL_X, 57),    # channel: three segments
        ("line", CHANNEL_X, 60, CHANNEL_X, 66),
        ("line", CHANNEL_X, 69, CHANNEL_X, 75),
        ("line", CHANNEL_X, 54, DRAIN_X, 54),      # drain tap
        ("line", DRAIN_X, 54, DRAIN_X, 45),
        ("line", CHANNEL_X, 72, DRAIN_X, 72),      # source tap
        ("line", DRAIN_X, 72, DRAIN_X, 81),
        ("line", CHANNEL_X, 63, DRAIN_X, 63),      # bulk tap
        ("line", DRAIN_X, 63, DRAIN_X, 63),
        ("line", 45, 63, GATE_X, 63),              # gate lead
        ("arrow", CHANNEL_X, 63, CHANNEL_X + 5, 63),  # bulk arrow, points in for n-channel
    ]


def _glyph_pmos():
    g = _glyph_nmos()
    # p-channel: bulk arrow points out of the channel
    g[-1] = ("arrow", CHANNEL_X + 5, 63, CHANNEL_X, 63)
    return g


class MosfetFactory:
    """Builds MOSFET CiComponents inside a Palette by cloning + rewriting 2N2222A."""

    def __init__(self, palette, base=None):
        self.pal = palette
        if base is None:
            try:
                base = palette.pick("2N2222A")
            except KeyError:                      # palette from another project: any BJT
                base = palette.pick_refdes("Q")
        self.base = base
        self._made = {}

    # ------------------------------------------------------------------ api ----
    def make(self, name, model_card, glyph, prefix, family, vth_display):
        if name in self._made:
            return name
        pal = self.pal
        src_item = pal.components[self.base]
        src_comp = src_item[0]
        src_comp_id = src_item.get("CiID")
        src_model_id = src_comp.get("Model")
        src_sym = next(it for it in pal.comp_objects if it.get("ID") == src_comp.get("SymCompID"))

        item = copy.deepcopy(src_item)
        comp = item[0]
        sym = copy.deepcopy(src_sym)

        self._rename_pins(comp, sym)
        self._set_model(comp, model_card, prefix, family, vth_display)
        self._redraw(sym, glyph)

        # new CiIDs so nothing aliases the transistor
        used = set()
        for it in list(pal.elements) + list(pal.comp_objects) + [item]:
            for e in it.iter():
                for k in ("CiID", "ID", "PortID", "SymCompID", "Model", "Component"):
                    v = e.get(k)
                    if v and v.isdigit():
                        used.add(v)
        # IDs for synthesized parts live in a range the Builder never hands out
        # (Builder._id() counts up from 500000000), otherwise a placed part and its
        # palette template can end up sharing CiIDs after remapping.
        nxt = [900000000]
        mapping = {}

        def next_id():
            while str(nxt[0]) in used:
                nxt[0] += 1
            v = str(nxt[0])
            nxt[0] += 1
            used.add(v)
            return v

        def remap(e):
            # CiComponent is the symbol -> component back-reference; leaving it out
            # leaves the synthesized symbol pointing at the donor BJT (dangling link,
            # Multisim crashes when it resolves the symbol's owner)
            for k in ("CiID", "ID", "PortID", "SymCompID", "Model", "Component",
                      "CiComponent"):
                v = e.get(k)
                if v and v.isdigit():
                    if v not in mapping:
                        mapping[v] = next_id()
                    e.set(k, mapping[v])
            for c in e:
                remap(c)

        remap(item)
        remap(sym)
        new_comp_id = item.get("CiID")          # wrapper id = the component's CiID
        sym[0].set("CiComponent", new_comp_id)  # symbol -> component, always consistent

        # clone the CiPort elements that this component owns
        for it in list(pal.elements):
            if (it.get("Class") == "CiPort"
                    and (it[0].get("Component") or "").replace("&ASC", "") in
                        (src_comp_id, mapping.get(src_comp_id))):
                pit = copy.deepcopy(it)
                old_pin = (pit[0].get("LocalName") or "").replace("&ASC", "")
                if old_pin in PIN_MAP:
                    pit[0].set("LocalName", "&ASC" + PIN_MAP[old_pin])
                remap(pit)                     # fresh ids first...
                pit[0].set("Component", new_comp_id)   # ...then stamp the owner once
                pal.elements.append(pit)

        model_item = None
        for it in pal.elements:
            if it.get("Class") == "CiModel" and it.get("CiID") == src_model_id:
                model_item = it
                break
        if model_item is not None:
            mit = copy.deepcopy(model_item)
            remap(mit)
            pal.elements.append(mit)
            comp.set("Model", mit.get("CiID"))
            self._patch_model(mit, model_card, prefix, family)

        pal.elements.append(item)
        pal.comp_objects.append(sym)
        pal.components[name] = item
        self._made[name] = name
        return name

    def add(self, name, model_card, glyph, prefix, family, vth):
        return self.make(name, model_card, glyph, prefix, family, vth)

    # ------------------------------------------------------------- internals ----
    def _rename_pins(self, comp, sym):
        for tag in ("CIITPinSymbolComp",):
            for pe in sym.iter(tag):
                old = (pe.get("PinName") or "").replace("&ASC", "")
                if old in PIN_MAP:
                    pe.set("PinName", "&ASC" + PIN_MAP[old])
        # port names on the CiPort elements are patched after remap in make()

    def _patch_model(self, model_item, model_card, prefix, family):
        """Rewrite the cloned CiModel so SPICE sees a MOSFET, not the BJT."""
        model_card = ms14build._flatten_card(model_card)
        cm = model_item[0]
        # the card must declare the name the CiModel carries, exactly as the donor does
        # ("2N2222A__BJT_NPN__1" in both places). A CiModel whose name and declaration
        # disagree expands under a name nothing references, and a second CiModel declaring
        # the same .MODEL leaves one copy's internal nodes floating ("singular matrix").
        name = prefix + "__" + family
        cm.set("LocalName", "&ASC" + name)
        attrs = cm.find("Attributes")
        card = attrs[1][0]
        card.set("String", "&ASC" + re.sub(r"(?im)^(\s*\.model\s+)\S+",
                                           lambda m: m.group(1) + name, model_card, count=1))
        params = attrs[2][0]
        for child in list(params):
            for it in list(child):
                child.remove(it)
        coll = attrs[4][0].find("strings")
        if coll is not None and len(coll):
            coll[-1].set("Value", "&ASCA0")

    def _set_model(self, comp, model_card, prefix, family, vth):
        attrs = comp.find("Attributes")
        # Attributes[1] = SPICE template, [4] = identification strings
        tmpl = attrs[1][0]
        # SPICE needs four nodes: m<ref> <drain> <gate> <source> <bulk> <model>.
        # The database template ties bulk to source ('%tS %tS'), so do the same.
        tmpl.set("String", "&ASCm%p %tD %tG %tS %tS %m ")
        coll = attrs[4][0].find("strings")
        # This block is the database row the part was placed from. Its card keeps a name
        # of its own (never the CiModel's): a row re-declaring the CiModel's name is a
        # second definition of one model (checksim.py C11).
        # per-instance name, so this row can never shadow the shared CiModel.
        row_card = re.sub(r"(?im)^(\s*\.model\s+)\S+",
                          lambda m: m.group(1) + prefix, ms14build._flatten_card(model_card), count=1)
        vals = ["&ASC" + family, "&ASC" + prefix, "&ASC" + family,
                "&ASCm" + prefix, "&ASC1", "&ASC" + row_card]
        for i, v in enumerate(vals):
            while len(coll) <= i:
                ET.SubElement(coll, "Item", {"Value": ""})
            coll[i].set("Value", v)
        coll2 = attrs[5][0].find("strings")
        coll2[0].set("Value", "&ASC48")
        coll2[1].set("Value", "&ASCProduct")
        coll2[2].set("Value", "&ASC" + family)
        coll2[4].set("Value", "&ASCm%d")
        coll2[5].set("Value", "&ASCm%p %tD %tG %tS %tS %m ")

    def _redraw(self, sym, glyph):
        """Replace the drawing primitives with a MOSFET glyph.

        Every primitive is a *clone of a primitive the GUI already wrote* (same donor
        symbol), so the attribute set - including the Transformer-M00..M21 matrix that
        Multisim needs - is guaranteed complete. Coordinates are the only thing edited.

        Multisim reads a symbol as: text/border entries + COD* drawing primitives +
        CIITPinSymbolComp entries. Pins stay where the donor put them (C 63,45 / B 45,63
        / E 63,81 -> D / G / S), so wires still land on the pin connectors.
        """
        # only the symbol-level drawing container: nested Objects inside a
        # CIITPinSymbolComp belong to that pin and must not be touched
        target = sym[0].find("Objects")
        line_proto = poly_proto = ellipse_proto = None
        for ch in target:
            cls = ch.get("Class")
            if cls == "CODLineComp" and line_proto is None:
                line_proto = ch
            elif cls == "CODPolygonComp" and poly_proto is None:
                poly_proto = ch
            elif cls == "CODEllipseComp" and ellipse_proto is None:
                ellipse_proto = ch

        # drop the donor BJT glyph; the package circle (if any) is kept as-is
        for ch in list(target):
            if ch.get("Class") in ("CODLineComp", "CODPolygonComp"):
                target.remove(ch)

        if line_proto is None:
            raise RuntimeError("donor symbol has no CODLineComp to clone")

        nextid = [950000000]

        def clone(proto):
            e = copy.deepcopy(proto)
            e.set("ID", str(nextid[0]))
            nextid[0] += 1
            target.append(e)
            return e[0]

        for g in glyph:
            kind, x0, y0, x1, y1 = g
            if kind == "line":
                el = clone(line_proto)
                el.set("pt0X", str(x0)); el.set("pt0Y", str(y0))
                el.set("pt1X", str(x1)); el.set("pt1Y", str(y1))
                el.set("ArrowAtSource", "0"); el.set("ArrowAtTarget", "0")
            elif kind == "arrow" and poly_proto is not None:
                el = clone(poly_proto)
                # closed triangle: tip at (x1,y1), base 6 units behind it
                bx = x0 + (x1 - x0) - 6 if x1 >= x0 else x1 + 6
                pts = [(x0, y0), (bx, y1 - 3), (bx, y1 + 3), (x0, y0)]
                el.set("ArrowAtSource", "0"); el.set("ArrowAtTarget", "0")
                child = el.find("Points")
                for it in list(child):
                    child.remove(it)
                for px, py in pts:
                    ET.SubElement(child, "Item", {"X": str(px), "Y": str(py)})


def mos_palette(path, glyph_donor=None):
    """Load a Palette and add MOSFET_N / MOSFET_P parts to it.

    `glyph_donor` is only used for the BJT glyph the MOSFET symbols are drawn from, so a
    palette can carry the *electrical* parts of one project and the glyphs of another.
    """
    pal = ms14build.Palette(path)
    f = MosfetFactory(pal)
    f.add("MOSFET_N", NMOS_MODEL, _glyph_nmos(), "2N7000", "MOS_N", "2.1")
    f.add("MOSFET_P", PMOS_MODEL, _glyph_pmos(), "BS250", "MOS_P", "-2.0")
    return pal
