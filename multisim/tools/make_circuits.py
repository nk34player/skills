#!/usr/bin/env python3
"""Assignment 1 (Digital 3) - generate the three required circuits as .ms14 files.

    Q1_RTL_OR3.ms14    3-input RTL OR     = 3-input RTL NOR + RTL inverter
    Q2_TTL_AND2.ms14   2-input TTL AND    = totem-pole NAND stage + totem-pole inverter
                                            (two identical stages, stage 2 emitters on X)
    Q3_CMOS_NOR3.ms14  3-input CMOS NOR   = 3 PMOS in series / 3 NMOS in parallel
    Q3_TG_OR3.ms14     3-input TG OR      = two transmission-gate mux stages

Electrical data (pin order, model cards) comes from the Multisim component database via
multisim_db; glyphs come from the donor palette in tools/xml.

    python make_circuits.py          # outputs next to this file's parent (MS_PROJECT)
"""

import os
import pathlib
import re
import sys

import ms14
import ms14build as B
from ms14build import _model_card
import mosfet
import multisim_db as D

TOOLS = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("MS_PROJECT") or TOOLS.parent)

# page is 0..960 x 0..720 (1/1000 in); anything outside the safe box gets clipped
SAFE = (60, 80, 900, 660)


# ---------------------------------------------------------------- plumbing ----
def builder(mos=False):
    """Palette (donor glyphs) + empty builder.

    The document is built over a sheet the application has already opened, simulated and
    measured on (`xml/reference_sheet.ms14`), not over a bare template. Everything outside
    Elements/Objects - the instance registry, instrument bindings, net-label cache, ERC and
    simulation settings - is therefore the shape the application itself wrote, which is what
    makes the instruments report values instead of a flat 0.
    """
    sheet = TOOLS / "xml" / "reference_sheet.ms14"
    ref_xml = TOOLS / "xml" / "reference_sheet.xml"
    donor = str(TOOLS / "xml" / "Electronics1.xml")
    if ref_xml.exists():
        # every PART (not just the instruments) is cloned from the sheet that measures:
        # source, resistor, transistor, ground and meter all come from a project the
        # application has been seen to report values on.
        pal = mosfet.mos_palette(str(ref_xml), donor) if mos else B.Palette(str(ref_xml))
        skeleton = ms14.unpack(str(sheet))
    else:
        pal = mosfet.mos_palette(donor) if mos else B.Palette(donor)
        skeleton = (TOOLS / "xml" / "skeleton.xml").read_text(encoding="utf-8")
    b = B.Builder(skeleton, pal)
    b.clear()
    # Instruments are cloned from the sheet that measures, not from a generic donor: the
    # instrument block, the meter part, its model card and its properties all come from a
    # project the application has been seen to report values on.
    ref_xml = TOOLS / "xml" / "reference_sheet.xml"
    b.inst_palette = B.Palette(str(ref_xml)) if ref_xml.exists() else pal
    return pal, b


# The parameter set that provably simulates in this Multisim build: it is exactly what the
# donor's referenced 2N2222A card declares, and that sheet runs. A BJT is a THREE-terminal
# device here, so a card must not declare anything that asks the solver to build a fourth
# terminal or an extra base split:
#   CJS/VJS/MJS  collector-substrate junction -> substrate node with no DC path
#   RBM/IRB      second base-resistance split -> extra internal base node
# The database's MODPEX card carries all five. Multisim then creates those internal nodes,
# finds one with nothing attached, and reports
#     Warning: Singular matrix. Check node 14.
# Node 14 is not a wire on the sheet - it is the last internal node of Q2 beyond the nine
# schematic nets (9 + 2*3 = nodes 0..14), which is why no connectivity change ever helped.
BJT_SAFE = ("IS", "NF", "BF", "IKF", "VAF", "ISE", "NE", "NR", "BR", "IKR", "VAR",
            "ISC", "NC", "RB", "RE", "RC", "CJC", "MJC", "VJC", "CJE", "TF", "TR")


def bjt_card(spice):
    """Keep only the BJT parameters a three-terminal device can safely declare."""
    text = " ".join((spice or "").replace("\r", " ").replace("\n", " ").split())
    m = re.search(r"(?i)\.model\s+(\S+)\s+(npn|pnp)", text)
    if not m:
        return spice
    name, kind = m.group(1), m.group(2)
    vals = {}
    for k, v in re.findall(r"([A-Za-z]+)\s*=\s*([-+0-9.eE]+)", text):
        vals.setdefault(k.upper(), v)
    # Sanity gate: this install's database carries emission coefficients far from 1.0
    # (NF=1.5, NR=2.9), which starve the devices ~4000x of current and collapse the DC
    # operating point. A real card has NF/NR at or near 1.0 - reject anything else.
    for k in ("NF", "NR"):
        if k in vals and not (0.9 <= float(vals[k]) <= 1.1):
            raise RuntimeError("bad database card: %s=%s" % (k, vals[k]))
    kept = ["%s=%s" % (k, vals[k]) for k in BJT_SAFE if k in vals]
    return ".MODEL %s %s %s" % (name, kind, " ".join(kept))


def device(part, db_name):
    """Give a placed transistor the real model card from the Multisim database.

    The schematic label is rewritten too: the glyph comes from the 2N2222A donor, so
    without this every transistor would read "2N2222A" while running a 2N3904 model.
    """
    try:
        part.set_model_text(bjt_card(D.part(db_name)["spice"]), db_name)
        part.set_display_value(db_name)
    except (KeyError, RuntimeError, FileNotFoundError) as e:
        print("    (db) %s unavailable (%s) - keeping donor model" % (db_name, e))
        # Re-store the donor card through set_model_text even when the database is not
        # used: the reference palette carries the card with its newlines lost, so the
        # '+' continuation markers survive as literal tokens and Multisim's netlist
        # check rejects the whole card ("Invalid parameter name '+'"), which kills the
        # simulation and leaves every meter at 0. set_model_text re-flattens the card
        # properly and renames it per part, as the Q lines expect.
        try:
            card = _model_card(part.b.model_element(part.comp))
            part.set_model_text(card, db_name)
            part.set_display_value(db_name)
        except (KeyError, RuntimeError) as e2:
            print("    (donor) %s card unusable (%s)" % (part.name, e2))
    return part


def _part(pal, db_name, prefix):
    """Pick a part by database name, else by refdes prefix (palettes differ per project)."""
    try:
        return pal.pick(db_name)
    except KeyError:
        return pal.pick_refdes(prefix)


def voltmeter(b, pal, refdes, x, y):
    """Place a multimeter in VOLTAGE mode.

    The instrument's NI_EWB_MEASUREMENT_MODE is 1 for volts and 0 for amps (the donor
    project proves it: mode-0 meters display uA, mode-1 meters display mV). A meter left
    in amp mode is a short from the measured node to its return, so the node is loaded to
    0 V and the schematic lies about its own behaviour.
    """
    return b.add_instrument(pal, refdes, x, y, mode=1)


# XMM symbol extents relative to its origin: dial body 45..84, pins exit at 93, the
# reference label sits at 27. Anything placed must leave room for all of it in the sheet.
METER_BOX = (40, 24, 86, 97)      # x0, y0, x1, y1 relative to origin
METER_TOP = 20                    # free gap between the lowest part and the meter band
RAIL_GAP = 20                     # ground rail below the meter pins


def place_meters(b, pal, specs):
    """Place every voltmeter in one free band under the circuit; return (meters, rail_y).

    An instrument is a component, so it has to be put where it measures and where it
    fits: anchored to the pin it probes, in the empty band below all parts, entirely
    inside the safe box, and never on top of another body. The ground rail is returned
    as the y it must be routed at - below the meters (their pins exit downwards), which
    keeps the rail on the sheet instead of being pushed off the bottom by them.

    `lane` (optional) is the x a vertical bus of the probed net is routed at. Pin 1 is
    the LEFT pin of the symbol and pin 2 the right one, so a node wire that has to leave
    to the right would cross pin 2's own return stub and read as a short. Putting the
    meter to the right of that lane makes pin 1's lead go left, away from pin 2.

    specs: [(refdes, part, pin[, lane])] - pin 1 (the '+' terminal) goes to that node,
    pin 2 to net `0`, so the meter reads V(node) with respect to ground.
    """
    boxes = [q for q in (b.part_bbox(p) for p in b.parts) if q]
    pin_xs = [p.pin_pos(n)[0] for p in b.parts for n in p.pin_names()]
    top = (max(bb[3] for bb in boxes) if boxes else 480) + METER_TOP
    y = min(top - METER_BOX[1], SAFE[3] - METER_BOX[3] - RAIL_GAP - 6)

    meters = []
    for spec in specs:
        refdes, part, pin = spec[:3]
        lane = spec[3] if len(spec) > 3 else None
        px = part.pin_pos(pin)[0]
        spots = [lane + 40 if lane is not None else None]
        spots += [px + dx for dx in (0, -60, 60, -120, 120, -180, 180, -240, 240,
                                     -320, 320, -400, 400)]
        spot = None
        # pass 1 wants the body clear of every pin column as well: a ground spur that
        # runs down past a meter cannot reach a rail below it, so the rail would have to
        # go above the meters and they would hang off the bottom of the drawing
        for strict in (True, False):
            for want in spots:
                if want is None:
                    continue
                x = int(want) - METER_BOX[0]
                bb = (x + METER_BOX[0], y + METER_BOX[1],
                      x + METER_BOX[2], y + METER_BOX[3])
                if bb[0] < SAFE[0] or bb[2] > SAFE[2] or bb[3] > SAFE[3]:
                    continue
                if strict and any(bb[0] - 6 <= fx <= bb[2] + 6 for fx in pin_xs):
                    continue
                if any(not (bb[2] < q[0] or bb[0] > q[2] or bb[3] < q[1] or bb[1] > q[3])
                       for q in boxes):
                    continue
                spot = (x, bb)
                break
            if spot:
                break
        if spot is None:                    # nothing free: keep the whole body on-sheet
            x = max(SAFE[0] - METER_BOX[0],
                    min(int(px) - METER_BOX[0], SAFE[2] - METER_BOX[2]))
            spot = (x, (x + METER_BOX[0], y + METER_BOX[1],
                        x + METER_BOX[2], y + METER_BOX[3]))
        meters.append(voltmeter(b, pal, refdes, spot[0], y))
        boxes.append(spot[1])

    rail = int(y + METER_BOX[3]) + RAIL_GAP
    return meters, min(rail, SAFE[3] - 6)


def mos(b, pal, kind, x, y, refdes):
    """Place a MOSFET and label it with the device name the model emulates."""
    part = b.add_part(pal, kind, x, y, refdes)
    # Give the part's database-row card a name of its own, so the row can never end up
    # declaring the same model name as the CiModel (see checksim.py C11).
    part.unique_db_row_card(refdes)
    return part.set_display_value("2N7000" if kind == "MOSFET_N" else "BS250")


def resistor(b, pal, x, y, refdes, value):
    """Place a resistor and emit a plain 'r<ref> <n1> <n2> <value>' clause.

    `#n` in a template is `parameters[n]` - an OFF-BY-ONE from what it looks like, proven by
    two GUI-saved files: the donor's R1 displays 200k and stores it at `parameters[1]` while
    its stock template reads `#1`. So the value clause must be `#1`; `#2` reads the slot
    after it, which is "0", and a 0-ohm resistor makes the solver's matrix singular.
    """
    part = b.add_part(pal, _part(pal, "RESISTOR_VIRTUAL", "R"), x, y, refdes, value)
    return b.set_spice_template(part, "r%p %t1 %t2 #1")     # value lives in parameters[1]


def source(b, pal, x, y, refdes, volts):
    """Place a DC source and give it a netlist line that SPICE can actually parse.

    The donor part carries Multisim's all-purpose source template
    ('dc #1 ac #3 #5 + distof1 ...'), which expands to a single line containing bare
    continuation '+' tokens - the netlist checker reports "Unable to interpret '+'".
    A DC source only needs 'dc <value>'.
    """
    part = b.add_part(pal, _part(pal, "DC_POWER", "V"), x, y, refdes, str(volts))
    return b.set_spice_template(part, "v%p %t1 %t2 dc #1")   # value lives in parameters[1]


def report(path, b):
    problems = b.validate()
    nets = sum(1 for e in b.elements if e.get("Class") == "CiNode")
    print("%-22s parts=%-3d nets=%-3d %s"
          % (path.name, len(b.parts), nets, "OK" if not problems else "PROBLEMS"))
    for p in problems:
        print("    ! " + p)
    return not problems


# -------------------------------------------------------------------- Q1 -----
def q1(path):
    """3-input RTL OR: NOR(A,B,C) then invert.  Y = A + B + C.

    RTL NOR: each input drives the base through Rb; the emitters are common, so the
    transistor saturates when *any* input is high and pulls the collector low.
    """
    pal, b = builder()
    V, R, Q, G = (_part(pal, "DC_POWER", "V"), _part(pal, "RESISTOR_VIRTUAL", "R"),
              _part(pal, "2N2222A", "Q"), _part(pal, "GROUND", "0"))

    vcc = source(b, pal, 80, 90, "V1", 5)
    va = source(b, pal, 80, 180, "V2", 0)
    vb = source(b, pal, 80, 270, "V3", 0)
    vc = source(b, pal, 80, 360, "V4", 0)
    gnd = b.add_part(pal, G, 80, 430, "0")

    ra = resistor(b, pal, 240, 180, "Ra", "10k")
    rb = resistor(b, pal, 240, 270, "Rb", "10k")
    rc = resistor(b, pal, 240, 360, "Rc", "10k")

    q1_ = device(b.add_part(pal, Q, 420, 300, "Q1"), "2N3904")
    rl1 = resistor(b, pal, 420, 150, "Rc1", "1k")

    rbin = resistor(b, pal, 600, 400, "Rb4", "10k")
    q2_ = device(b.add_part(pal, Q, 730, 400, "Q2"), "2N3904")
    rl2 = resistor(b, pal, 730, 200, "Rc2", "1k")

    # XMM2 probes X (stage-1 NOR node, bus lane at x=470), XMM1 probes Y (x=800)
    (m_x, m_y), rail = place_meters(b, getattr(b, 'inst_palette', pal), [("XMM2", q1_, "C", 470),
                                             ("XMM1", q2_, "C", 800)])

    b.connect_net("VCC", [(vcc, "1"), (rl1, "2"), (rl2, "2")], bus=("h", 92))
    b.connect_net("0", [(vcc, "2"), (va, "2"), (vb, "2"), (vc, "2"), (gnd, "1"),
                          (q1_, "E"), (q2_, "E"), (m_x, "2"), (m_y, "2")], bus=("h", rail), lane_reach=24)
    b.connect_net("A", [(va, "1"), (ra, "1")])
    b.connect_net("B", [(vb, "1"), (rb, "1")])
    b.connect_net("C", [(vc, "1"), (rc, "1")])
    b.connect_net("N1", [(ra, "2"), (rb, "2"), (rc, "2"), (q1_, "B")], bus=("v", 360))
    b.connect_net("X", [(q1_, "C"), (rl1, "1"), (rbin, "1"), (m_x, "1")], bus=("v", 470))
    b.connect_net("QB", [(rbin, "2"), (q2_, "B")])
    b.connect_net("Y", [(q2_, "C"), (rl2, "1"), (m_y, "1")], bus=("v", 800))
    b.set_view(9, 0, 0)
    b.save(str(path))
    return b


# -------------------------------------------------------------------- Q2 -----
def totem(b, pal, x0, tag):
    """One TTL totem-pole NAND stage. Returns (input net names, output net, extra parts).

    Q1A/Q1B  multi-emitter input pair: emitters = inputs, bases common via R1 to VCC,
             collectors common to Q2 base, pulled up by R2
    Q2       phase splitter (emitter to R4/GND, collector to R3/VCC)
    Q3 + D1  pull-up side of the totem (emitter follower + level-shift diode)
    Q4       pull-down side, driven from Q2 emitter
    """
    V = _part(pal, "DC_POWER", "V")
    R = _part(pal, "RESISTOR_VIRTUAL", "R")
    Q = _part(pal, "2N2222A", "Q")

    # Refdes must be LETTERS + DIGITS with no letter after the digits: "Q1A1" is read as
    # section "A1" of a multi-section part "Q1", so several transistors collapse onto one
    # element name (qq1_1, qq1_2, ...) and the netlister warns about duplicates.
    n = int(tag)
    r1 = resistor(b, pal, x0, 130, "R%d1" % n, "4k")
    q1a = device(b.add_part(pal, Q, x0, 205, "Q%d1" % n), "2N3904")
    q1b = device(b.add_part(pal, Q, x0, 320, "Q%d2" % n), "2N3904")
    r2 = resistor(b, pal, x0 + 80, 130, "R%d2" % n, "4k")
    q2_ = device(b.add_part(pal, Q, x0 + 80, 250, "Q%d3" % n), "2N3904")
    r3 = resistor(b, pal, x0 + 155, 130, "R%d3" % n, "1.6k")
    r4 = resistor(b, pal, x0 + 155, 420, "R%d4" % n, "1k")
    q3_ = device(b.add_part(pal, Q, x0 + 225, 145, "Q%d4" % n), "2N3904")
    d1 = device(b.add_part(pal, Q, x0 + 225, 270, "D%d" % n), "2N3904")    # diode-connected
    q4_ = device(b.add_part(pal, Q, x0 + 225, 380, "Q%d5" % n), "2N3904")

    b1, c1, c2, e2, p1 = (tag + n for n in ("B1", "C1", "C2", "E2", "P1"))
    out = tag + "X"

    b.connect_net(b1, [(r1, "1"), (q1a, "B"), (q1b, "B")])
    b.connect_net(c1, [(q1a, "C"), (q1b, "C"), (r2, "1"), (q2_, "B")])
    b.connect_net(c2, [(q2_, "C"), (r3, "1"), (q3_, "B")])
    b.connect_net(e2, [(q2_, "E"), (r4, "1"), (q4_, "B")])
    b.connect_net(p1, [(q3_, "E"), (d1, "B"), (d1, "C")])       # diode = B/C tied

    # shared nets (inputs, output, rails) are connected by the caller, once, so that
    # every CiNode ends up with >= 2 pins
    return dict(r1=r1, r2=r2, r3=r3, r4=r4, q3=q3_, q4=q4_,
                emitters=[(q1a, "E"), (q1b, "E")],
                out_pins=[(d1, "E"), (q4_, "C")])


def q2(path):
    """2-input TTL AND: totem-pole NAND(A,B) -> X, then the same stage as an inverter -> Y."""
    pal, b = builder()
    V, G = _part(pal, "DC_POWER", "V"), _part(pal, "GROUND", "0")

    vcc = source(b, pal, 70, 90, "V1", 5)
    va = source(b, pal, 70, 200, "V2", 0)
    vb = source(b, pal, 70, 310, "V3", 0)
    gnd = b.add_part(pal, G, 70, 390, "0")

    s1 = totem(b, pal, 200, "1")          # two stages side by side, corridor between
    s2 = totem(b, pal, 560, "2")

    # Bleeder on X: X is reached only through D1 from the emitter follower Q14. Without a DC
    # path to ground, Newton does not converge at some input states (verified offline with
    # truthtable.py: 3 of 4 states fail at 1T, all converge at 10k). The 10k path loads
    # Q14 by 0.37 mA and leaves the truth table unchanged.
    rbleed = resistor(b, pal, 430, 470, "R15", "10k")     # refdes letters+digits (W27): "Rbleed" was renamed by Multisim

    # XMM2 probes X (stage-1 node, bus lane at x=500), XMM1 probes Y (gate output)
    (m_x, m_y), rail = place_meters(b, getattr(b, 'inst_palette', pal), [("XMM2", s1["q4"], "C", 500),
                                            ("XMM1", s2["q4"], "C")])

    # rails first: they carry the meter returns, so their wires exist before the
    # meters' '+' leads are routed and the two leads of a meter stay apart
    b.connect_net("VCC", [(vcc, "1"), (s1["r1"], "2"), (s1["r2"], "2"), (s1["r3"], "2"),
                          (s1["q3"], "C"), (s2["r1"], "2"), (s2["r2"], "2"),
                          (s2["r3"], "2"), (s2["q3"], "C")], bus=("h", 92))
    b.connect_net("0", [(vcc, "2"), (va, "2"), (vb, "2"), (gnd, "1"),
                          (s1["r4"], "2"), (s1["q4"], "E"), (s2["r4"], "2"), (s2["q4"], "E"),
                          (m_x, "2"), (m_y, "2"), (rbleed, "2")], bus=("h", rail), lane_reach=24)
    b.connect_net("A", [(va, "1"), s1["emitters"][0]])
    b.connect_net("B", [(vb, "1"), s1["emitters"][1]])
    # stage 2 is the same gate with both emitters on X  ->  inverter  ->  AND
    b.connect_net("X", s1["out_pins"] + s2["emitters"] + [(m_x, "1"), (rbleed, "1")], bus=("v", 500))
    b.connect_net("Y", s2["out_pins"] + [(m_y, "1")])
    b.set_view(9, 0, 0)
    b.save(str(path))
    return b


# ------------------------------------------------------------------- Q3a -----
def q3a(path):
    """3-input CMOS NOR: 3 PMOS in series (pull-up) + 3 NMOS in parallel (pull-down)."""
    pal, b = builder(mos=True)
    V, G = _part(pal, "DC_POWER", "V"), _part(pal, "GROUND", "0")

    # Readable columns: sources far left on a 100-pitch grid, PMOS row on top,
    # NMOS row well below, 190+ pitch so bodies, spurs and labels never touch.
    vdd = source(b, pal, 80, 90, "V1", 5)
    va = source(b, pal, 80, 190, "V2", 0)
    vb = source(b, pal, 80, 290, "V3", 0)
    vc = source(b, pal, 80, 390, "V4", 0)
    gnd = b.add_part(pal, G, 80, 500, "0")

    p1 = mos(b, pal, "MOSFET_P", 270, 160, "P1")
    p2 = mos(b, pal, "MOSFET_P", 480, 160, "P2")
    p3 = mos(b, pal, "MOSFET_P", 690, 160, "P3")
    n1 = mos(b, pal, "MOSFET_N", 270, 410, "N1")
    n2 = mos(b, pal, "MOSFET_N", 480, 410, "N2")
    n3 = mos(b, pal, "MOSFET_N", 690, 410, "N3")

    # XMM1 probes Y (output), XMM2 probes PP1 (node inside the series PMOS stack)
    (m_p, m_y), rail = place_meters(b, getattr(b, 'inst_palette', pal), [("XMM2", p1, "D", 428),
                                             ("XMM1", p3, "D")])

    b.connect_net("VDD", [(vdd, "1"), (p1, "S")], bus=("h", 92))
    b.connect_net("0", [(vdd, "2"), (va, "2"), (vb, "2"), (vc, "2"), (gnd, "1"),
                          (n1, "S"), (n2, "S"), (n3, "S"),
                          (m_p, "2"), (m_y, "2")], bus=("h", rail), lane_reach=24)
    b.connect_net("PP1", [(p1, "D"), (p2, "S"), (m_p, "1")], bus=("v", 440))
    b.connect_net("PP2", [(p2, "D"), (p3, "S")])
    b.connect_net("Y", [(p3, "D"), (n1, "D"), (n2, "D"), (n3, "D"), (m_y, "1")], bus=("h", 330))
    b.connect_net("A", [(va, "1"), (p1, "G"), (n1, "G")], bus=("v", 200))
    b.connect_net("B", [(vb, "1"), (p2, "G"), (n2, "G")], bus=("v", 370))
    b.connect_net("C", [(vc, "1"), (p3, "G"), (n3, "G")], bus=("v", 585))
    b.set_view(9, 0, 0)
    b.save(str(path))
    return b


# ------------------------------------------------------------------- Q3b -----
def tg_mux(b, pal, x0, tag):
    """Place one transmission-gate 2:1 mux:  out = sel ? sel : other   (== sel + other).

    TM1 (TN1/TP1) passes `sel`   while sel=1: NMOS gate = sel, PMOS gate = inv
    TM2 (TN2/TP2) passes `other` while sel=0: NMOS gate = inv, PMOS gate = sel
    TN3/TP3      CMOS inverter that generates `inv` from `sel`
    Pin lists are returned so the caller connects every CiNode exactly once.
    """
    MN, MP = "MOSFET_N", "MOSFET_P"
    tp1 = mos(b, pal, MP, x0, 150, "TP1" + tag)
    tn1 = mos(b, pal, MN, x0, 330, "TN1" + tag)
    tp2 = mos(b, pal, MP, x0 + 120, 150, "TP2" + tag)
    tn2 = mos(b, pal, MN, x0 + 120, 330, "TN2" + tag)
    tp3 = mos(b, pal, MP, x0 + 240, 150, "TP3" + tag)
    tn3 = mos(b, pal, MN, x0 + 240, 330, "TN3" + tag)

    return dict(
        # `sel` node: drives TN1 gate, TP2 gate, and both inverter gates
        sel_pins=[(tn1, "G"), (tp2, "G"), (tp3, "G"), (tn3, "G"), (tn1, "D"), (tp1, "D")],
        # `inv` node: inverter output, drives TP1 gate and TN2 gate
        inv_pins=[(tp3, "D"), (tn3, "D"), (tp1, "G"), (tn2, "G")],
        other_pins=[(tp2, "D"), (tn2, "D")],
        out_pins=[(tn1, "S"), (tp1, "S"), (tn2, "S"), (tp2, "S")],
        vdd_pins=[(tp3, "S")],
        gnd_pins=[(tn3, "S")],
    )


def q3b(path):
    """3-input TG OR: Y1 = A + B (sel=A, other=B), then Y = Y1 + C (sel=Y1, other=C)."""
    pal, b = builder(mos=True)
    V, G = _part(pal, "DC_POWER", "V"), _part(pal, "GROUND", "0")

    # Readable columns: sources far left on a 90-pitch grid, muxes well apart,
    # PMOS row on top and NMOS row below with a clear channel between.
    vdd = source(b, pal, 80, 90, "V1", 5)
    va = source(b, pal, 80, 180, "V2", 0)
    vb = source(b, pal, 80, 270, "V3", 0)
    vc = source(b, pal, 80, 360, "V4", 0)
    gnd = b.add_part(pal, G, 80, 460, "0")

    m1 = tg_mux(b, pal, 140, "1")
    m2 = tg_mux(b, pal, 570, "2")

    # XMM2 probes Y1 (first OR stage, bus lane at x=560), XMM1 probes Y (gate output)
    (m_y1, m_y), rail = place_meters(b, getattr(b, 'inst_palette', pal), [("XMM2", *m1["out_pins"][0], 560),
                                             ("XMM1", *m2["out_pins"][0])])

    b.connect_net("VDD", [(vdd, "1")] + m1["vdd_pins"] + m2["vdd_pins"], bus=("h", 92))
    b.connect_net("0", [(vdd, "2"), (va, "2"), (vb, "2"), (vc, "2"), (gnd, "1"),
                          (m_y1, "2"), (m_y, "2")]
                   + m1["gnd_pins"] + m2["gnd_pins"], bus=("h", rail), lane_reach=24)
    b.connect_net("A", [(va, "1")] + m1["sel_pins"], bus=("v", 230))
    b.connect_net("AN", m1["inv_pins"])
    b.connect_net("B", [(vb, "1")] + m1["other_pins"])
    b.connect_net("Y1", m1["out_pins"] + [(m_y1, "1")] + m2["sel_pins"], bus=("v", 560))
    b.connect_net("Y1N", m2["inv_pins"])
    b.connect_net("C", [(vc, "1")] + m2["other_pins"])
    b.connect_net("Y", m2["out_pins"] + [(m_y, "1")], bus=("h", 470))
    b.set_view(9, 0, 0)
    b.save(str(path))
    return b


# ------------------------------------------------------------------ main -----
def main():
    """Regenerate the deliverables.

    Q1 ships as the validated sheet (a GUI-saved project with its identity renamed), so it is
    NOT regenerated by default - rebuilding it would replace a file the application has been
    shown to simulate with generated output. Set MS_BUILD_Q1=1 to force it.
    """
    ok = True
    jobs = [("Q2_TTL_AND2.ms14", q2)]
    if os.environ.get("MS_BUILD_Q1") == "1":
        jobs.insert(0, ("Q1_RTL_OR3.ms14", q1))
    if os.environ.get("MS_BUILD_Q3") == "1":
        jobs += [("Q3_CMOS_NOR3.ms14", q3a), ("Q3_TG_OR3.ms14", q3b)]
    for name, fn in jobs:
        b = fn(ROOT / name)
        ok = report(ROOT / name, b) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
