# multisim — Generate and manipulate NI Multisim .ms14 circuit files


## Critical placement constraints

**⚠️ ALWAYS start component placement from minimum (10, 10) offset from page origin (0, 0)**

Multisim page bounds: (0, 0) to (960, 720) in 1/1000 inch. Parts placed outside safe zone (60, 80) to (900, 660) will be clipped or dropped.

**Start every layout at (10, 10)** and add spacing from there.

## When to use

- User mentions "Multisim", ".ms14", "circuit simulation", "schematic generation"
- Task involves creating/editing/analyzing NI Multisim project files
- Building digital/analog circuits programmatically (RTL, TTL, CMOS logic gates)
- Need to generate circuit files without manual GUI interaction
- Reverse-engineering or inspecting existing .ms14 project structure

Do NOT use for generic SPICE netlists (use this only for Multisim's proprietary format).

## What this skill provides

Complete pipeline for .ms14 file generation:
- Unpack/pack .ms14 container (PKWARE DCL implode compression)
- Parse and manipulate Electronics Workbench XML schema
- Clone parts from donor projects (resistors, transistors, MOSFETs, sources, ground)
- Place components, wire nets, add instruments (multimeters)
- Validate electrical connectivity and geometry before saving
- Round-trip verification through Multisim

## Core capabilities

1. **Container codec**: `ms14.py` — byte-exact unpacking/packing with PKWARE DCL
2. **Circuit builder**: `ms14build.py` — part placement, wiring, net management
3. **Part extraction**: `Palette` class indexes donor projects to clone components
4. **MOSFET support**: `mosfet.py` — adds NMOS/PMOS from donor files
5. **Validation**: geometry checks, net connectivity, pin membership
6. **Automation**: PowerShell scripts for Multisim GUI control (open, save, screenshot)

## Installation paths

Paths differ per machine, per Multisim version and per install location. This skill uses
placeholders — resolve them once at the start of a session, then use the variables.

| Placeholder | Meaning | Windows default |
|-------------|---------|-----------------|
| `<MS_HOME>` | Multisim install root | `%ProgramFiles(x86)%/National Instruments/Circuit Design Suite <ver>/` |
| `<MS_DATA>` | per-machine data (holds the real database) | `%ProgramData%/National Instruments/Circuit Design Suite/<ver>/` |
| `<MS_USER>` | per-user data | `%APPDATA%/National Instruments/Circuit Design Suite/<ver>/` |
| `<MS_SAMPLES>` | shipped sample projects | `%PUBLIC%/Documents/National Instruments/Circuit Design Suite <ver>/samples/` |
| `<SKILL_DIR>` | this skill's directory, wherever it is installed | — |
| `<PROJECT>` | the working project (`.ms14` outputs land here) | — |

`<ver>` is the installed version (`14.2`, `14.3`, …). Discover everything instead of
assuming — drive letter, bitness and version all vary:

```python
import glob, os

def ms_paths():
    """Resolve Multisim paths on any install."""
    roots = [os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
             os.environ.get("ProgramFiles", r"C:\Program Files")]
    home = next((p for r in roots
                 for p in sorted(glob.glob(os.path.join(r, "National Instruments",
                                                        "Circuit Design Suite*")))
                 if os.path.isdir(p)), None)
    data = sorted(glob.glob(os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                                         "National Instruments", "Circuit Design Suite*",
                                         "database")))
    user = sorted(glob.glob(os.path.join(os.environ.get("APPDATA", ""), "National Instruments",
                                         "Circuit Design Suite*", "database")))
    samples = sorted(glob.glob(os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"),
                                            "Documents", "National Instruments",
                                            "Circuit Design Suite*", "samples")))
    return {"ver": os.path.basename(home).split()[-1] if home else "",
            "home": home,
            "data": data[-1] if data else None,
            "user": user[-1] if user else None,
            "samples": samples[-1] if samples else None}
```

```bash
# shell equivalent (Git Bash)
ls "/c/Program Files (x86)/National Instruments/" | grep "Circuit Design Suite"  # versions
ls "$PROGRAMDATA/National Instruments/Circuit Design Suite/"*/database/           # MSCOMP_*.PRD
```

⚠️ Never assume the drive, the 32/64-bit `Program Files` folder, or the version number.
Several releases install side by side and each has its own database folder — the tools
must glob, not hardcode.

**Project tools** live in `<SKILL_DIR>/tools/` (shipped with this skill) or
`<PROJECT>/tools/`. Scripts take paths from the caller; `make_circuits.py` reads its output
folder from the `MS_PROJECT` environment variable, falling back to its own parent folder.

| File | Purpose |
|------|---------|
| `pklib.py` | PKWARE DCL implode/explode (do NOT replace with zlib) |
| `ms14.py` | Container: `unpack(path)→xml`, `pack(xml,path)` |
| `ms14build.py` | `Palette` (index parts) + `Builder` (place/wire/save) |
| `mosfet.py` | Extend palette with MOSFET parts |
| `make_circuits.py` | Reference generators for the circuit families below |
| `xml/reference_sheet.ms14` | project base **that measures** - document layer and instruments are taken from it |
| `xml/reference_sheet.xml` | unpacked form of the above, for `Palette` |
| `xml/skeleton.xml` | last-resort empty template (identity `Skeleton`, scrubbed at save) |
| `xml/Electronics1.xml` | glyph/part donor, GUI-saved control for the structural tests |
| `wiregraph.py` | wire-level connectivity: CONNECTED or SPLIT/ALONE (W33) |
| `multisim_netlist.py` | Multisim's own netlist via COM: MATCH or SPLIT/SHORT (W34) |
| `spice_check.py` | independent ngspice .op truth table (needs `scoop install ngspice`) |
| `truthtable.py` | offline dcsolve truth table (oracle, W32) |
| `dcsolve.py` | DC operating point solver (validated, W32) |

## Quick reference

### Unpack/inspect existing project

```bash
cd tools
python ms14.py dump              # unpack all ../Multisim_old_project/*.ms14 → xml/
python -c "import ms14; print(ms14.unpack('<in>.ms14')[:500])"
```

### Build new circuit from scratch

```python
import ms14build as B

# Index donor parts
pal = B.Palette("<SKILL_DIR>/tools/xml/<donor>.xml")      # glyph donor project
skel = open("<SKILL_DIR>/tools/xml/<skeleton>.xml").read()   # empty-sheet project
b = B.Builder(skel, pal)
b.clear()

# Place parts (x,y in 1/1000 inch, page is 0-960 × 0-720)
r1 = b.add_part(pal, pal.pick("RESISTOR_VIRTUAL"), 300, 200, "R1", "10k")
v1 = b.add_part(pal, pal.pick("DC_POWER"), 150, 200, "V1", "5")
g1 = b.add_part(pal, pal.pick("GROUND"), 150, 300, "0")
q1 = b.add_part(pal, pal.pick("<bjt>"), 430, 330, "Q1")

# Wire nets (pins identified by name: R "1"=left "2"=right, Q "B"/"C"/"E")
b.connect_net("VCC", [(v1, "1"), (r1, "2")], bus=("h", 40))  # horizontal bus at y=40
b.connect_net("0", [(v1, "2"), (g1, "1"), (q1, "E")], bus=("h", 700))
b.connect_net("OUT", [(r1, "1"), (q1, "C")])

# Add instrument: mode=1 is VOLTS, mode=0 is AMPS (see the warning below)
xmm = b.add_instrument(pal, "XMM1", 500, 400, mode=1)   # DC voltmeter
b.connect_net("<node>", [(xmm, "1")])                   # pin 1 = + terminal
b.connect_net("0", [(xmm, "2")])                        # pin 2 = return

# Validate and save
problems = b.validate()  # checks: net size ≥2, all pins netted, geometry in bounds
if not problems:
    b.save("<out>.ms14")
    # Run structural tests to catch model reference issues
    import subprocess
    result = subprocess.run(["python", "tools/test_files.py", "<out>.ms14"], 
                          capture_output=True, text=True)
    if result.returncode != 0:
        print("Structural test failed:", result.stdout)
else:
    print("Validation failed:", problems)
```

### Add MOSFETs (NMOS/PMOS)

```python
import mosfet
pal = mosfet.mos_palette("<SKILL_DIR>/tools/xml/<donor>.xml")  # auto-extends with MOSFET_N/MOSFET_P
n1 = b.add_part(pal, "MOSFET_N", 300, 400, "N1")
p1 = b.add_part(pal, "MOSFET_P", 500, 200, "P1")
# Pins: "D" (drain), "G" (gate), "S" (source)
```

### Model lifecycle: definition, reference, registration

Any time you place a part that needs a SPICE model (BJT, MOSFET, diode, meter), follow this **exact** sequence:

#### 1. Let the Builder own model identities

`CiID` lives on the wrapper `Item` (`Elements/Item[@Class=CiModel]`), **not** on the inner `CiModel` element (canonical files leave the inner one without any `CiID`). Never stamp it by hand - add parts via `add_part` / `device()` / `set_model_text` and let `Builder.save()` allocate wrapper ids and rebuild `CiCircuit/Models|Components|Nodes` from the live table:

```python
# WRONG: hand-patching ids with raw ElementTree
model.set("CiID", "500000200")   # stamps the INNER element Multisim never tags;
                                     # tests still pass, the file is non-canonical

# RIGHT: declare intent, let save() wire the ids
q = b.add_part(pal, pal.pick("BJT_NPN"), 400, 300, "Q1")
device(q, "2N3904")   # real card + display value; save() registers the model
b.save(path)           # rebuilds Models/Components/Nodes with <Item CiID="..."/>
```

#### 2. Register the model with the circuit

Every model that a component uses must be listed in `CiCircuit/Models`. The list uses `<Item CiID="..."/>` structure:

```python
# The right structure: <Item CiID="..."/> with bare ID (no &ASC prefix)
for circuit in root.iter('CiCircuit'):
    models = circuit.find('Models')
    if models is not None:
        models.clear()
        for model_id in all_model_ids:
            item = ET.SubElement(models, 'Item')
            item.set('CiID', model_id)  # bare ID: "500000200", not "&ASC500000200"

# WRONG structures that cause "Singular matrix":
# <Item Value="&ASC500000200"/>     <- uses Value, not CiID
# <Item CiID="&ASC500000200"/>      <- prefixes with &ASC when bare ID is needed
# missing <Item/> entirely           <- model defined but not registered
```

#### 3. Verify with tests

Always run the structural suite before opening in Multisim:

```bash
cd tools
python test_files.py <out>.ms14          # T4 checks CiModel registration
python checknets.py <out>.ms14           # all nets have ≥2 pins
```

**What T4 does:**
- For each component, find its `Model` attribute (a model CiID)
- Look up that CiID in the models table
- Verify the model is listed in `CiCircuit/Models`
- If any of these fail, the circuit will report "Singular matrix: node X floating"

#### Prevention checklist

```
M1  every CiModel WRAPPER Item carries the CiID; the inner CiModel element carries none (do not stamp it)
M2  every component's Model attribute matches an existing wrapper CiID
M3  CiCircuit/Models contains all model CiIDs that components reference
M4  CiCircuit/Models uses <Item CiID="..."/> not <Item Value="..."/>
M5  no model CiID is shared between two different CiModel wrappers
M6  model CiIDs do not overlap with component/port/junction id ranges
M7  never hand-patch a shipped file with raw ElementTree + ET.tostring - regen via the generator so save() rebuilds M2-M4 itself
```

### Quick fixer for "Singular matrix"

Debug in this order. The first step is the one that actually found the last two bugs; the
others only rule things out.

1. **Element-type parity against a GUI-saved file (W19) - do this first.** For every
   `Class`, compare the attribute-group count per instance with a reference the application
   saved. One class collapsing to `0` groups is the defect:
   `CiComponent [47,53]  CiPort [41]  CiModel [3,5]  CiNode [33]  CiCircuit [0]`.
   A `CiNode` with an empty `<Attributes/>` has no reference flag, so **the netlist checks
   clean (`0 error(s), 0 warning(s)`) and the solve still cancels**. Guard: test T22.
2. **`python netlist.py <file>` - read the values, not just the shape.** Every `r` line must carry the real resistance and every `v` its real voltage. A `0` is the W21 off-by-one and makes the matrix singular while the netlist validates. Then `python dcsolve.py <file>` (which uses the same expansion): SOLVED = the file's own topology is sound, so the cause
   is on the application side of the expansion (payloads, cards, instrument mode).
   SINGULAR = a genuine connectivity problem; go to the net audits (T18/T20, 
   `netlist.py --check`).
3. **Diff against a working file with the same toolchain.** Compare what is *identical* as
   well as what differs: for the Q1 bug, topology, all 53 component groups, all 41 port
   groups and every wire coordinate matched the working reference project - only the net
   payload was missing. "Everything else matches" is what localises the fault.
4. **Do the node arithmetic.** `node N > nets-1` means a device-internal node
   (`(N - (nets-1))` counts solver-built nodes past the schematic, W18). With **no**
   reference node at all the number is meaningless and moves with schematic size - that
   wander is the signature of W19, not of a wire.
5. **Count the template's name in the output (W22e).** `ms14.unpack(out).count(old_name)` must be 0, and `Project/@Name`, `DesignSheet/@Title`, `RefDesInfoContainer/@CIR` and every instrument key must equal the file stem - that one string decides instrument binding and, if renamed in only one place, crashes the app.
6. **Second opinion from the application.** The Nets spreadsheet listing one net per pin
   (14 nets for 14 pins) while the file declares 5 means the netlister could not group pins
   at all - the drawing will still look perfect.

### Wiring strategies

**Point-to-point** (2 pins): simple L-shaped wire
```python
b.connect_net("A", [(part1, "1"), (part2, "2")])
```

**Multi-pin net** (3+ pins): star from centroid hub
```python
b.connect_net("VCC", [(v1, "1"), (r1, "2"), (r2, "2"), (r3, "2")])
```

**Rail/bus** (supply, ground): horizontal or vertical trunk + spurs
```python
b.connect_net("VCC", [...pins...], bus=("h", 40))    # horizontal at y=40
b.connect_net("N1", [...pins...], bus=("v", 360))   # vertical at x=360
```

Use `bus=` for any net with 4+ pins or supply rails — keeps layout readable.

### The recipe: a file that simulates AND measures

Everything below was found the hard way - each line is a defect that produced a *silent* failure
(the netlist validated every time). Follow it for every generated sheet. Sections W17-W25 and
tests T19, T21-T25 enforce it.

**0. Start from a project that already measures.** Use it as the document base and clone the instruments from it; rebuild its registry, pin table, per-refdes records and net labels for your own circuit (W26). A bare template's document layer cannot be patched into one that works.

**0b. Name every part `[A-Za-z]+[0-9]+`.** A trailing letter+digit (`Q1A1`) is read as a
multi-section suffix, so those parts merge into one element - a warning, not an error, and a
stage silently loses its wiring (W27).

**1. Payloads, per element class.** Never synthesize a container; clone one the application wrote.

```
CiComponent 47/53 groups | CiPort 41 | CiModel 3/5 | CiNode 33 | CiCircuit 0
```

- a `CiNode` with an empty `<Attributes/>` leaves the net unreferenced -> `Singular matrix` (W19, T22)
- attribute-group parity per class is the fastest diagnosis there is (W19)

**2. Net "0" is the reference.** Name the ground net exactly `0`, put the ground symbol on it, and
set the CiNode ground flag (group 16, one `CiaDOUBLE`) on that net and nowhere else (W17, T19, T22).

**3. Values live in `parameters[1]`, and `#n` means `parameters[n]`.** The offset is real: `#1` is
the second slot, `#0` is a dummy. A template reading `#2` emits `0` -

```
r<ref> <n1> <n2> 0      a zero-ohm resistor -> 1/0 -> singular matrix, netlist "0 errors"
```

Keep the numeric `doubles` mirror in step with the string list, or a clone silently runs at the
donor's value (W21, T23).

**4. Every corner shares one object; every T gets a junction (W33).** Two wires meet only when both reference the same `CODPinComp`. Position coincidence alone joins nothing. `wiregraph.py` must print CONNECTED.

**5. Index the sheet by class.** `ReferencedComponents` names wires as
`CIITLinkComp`, pins as `CIITPinConnectorComp`, labels as `CODNodeTextComp`; only connection points
are `CODPinComp`; one net-label object per NET, its `Links` naming every wire of that net.

**6. The document identity is the output file name.** It is stored six times - `Project/@Name`,
`Sheet/@SheetName`, `DesignSheet/@Title`, `RefDesInfoContainer/@CIR`, every
`RefDesInfoData/@RefDes` path, and the instrument keys. Rename textually over the finished XML to
the file stem, and scrub the template project's own name (W22e, T24):

```python
xml = self.xml()
stem = os.path.splitext(os.path.basename(path))[0]
for old in {self.sheet_name, "Skeleton"}:
    if old and old != stem:
        xml = xml.replace(old, stem)
```

**7. Instruments are a protocol, not a symbol.** All five must hold or the dial stays at `0`:

| Item | Required value |
|------|----------------|
| binding key | `CSourceSymbolCollectNode@CompLongName = "<refdes>#1/<sheet>:"`, sheet == `DesignSheet/@Title` (W22, T24) |
| model name | `X<refdes>_<document number>` (`XXMM1_278580792`); a made-up name netlists as an ordinary subcircuit (W23) |
| card | `.subckt <same name> 2 1  I_multi_meter 1 2 DC 0  R_multi_meter 2 1 1e9 .ends` |
| mode | `NI_EWB_MEASUREMENT_MODE` 1 = volts / 0 = amps, matching `R_multi_meter` 1e9 vs ~1e-5 (T21) |
| latch | `NI_EWB_CURRENTDISPLAYDATA_VALUE` holds a formatted value **with unit** (`"0 V"`) |

**8. Then verify - in this order, before opening the application.**

```bash
python test_files.py --ref <control> <out>.ms14   # T1-T25 structural + payloads + identity
python netlist.py <out>.ms14                      # the VALUES, not just the shape
python truthtable.py <out>.ms14 --in <vsrc..> --out <nets..>   # truth table (oracle, W32)
python wiregraph.py <out>.ms14                   # CONNECTED: the editor's wire joins (W33)
python multisim_netlist.py <out>.ms14            # MATCH: Multisim's own netlist (W34)
python dcsolve.py <out>.ms14                      # SOLVED / SINGULAR
python preview.py <out>.ms14 --no-png             # cross / shorts / open / stack
python checknets.py checkjoins.py <out>.ms14      # no net-to-net contact, no doubled wires
python checkmeterroles.py <out>.ms14              # which net each meter terminal lands on
python checksim.py <out>.ms14                     # C1-C14 would the app netlist it at all
```

**Failure -> one line, then fix exactly that:**

| symptom | cause | section |
|---------|-------|---------|
| `Singular matrix ... floating with respect to net 0` | wire islands first (W33), then net payload / pin with no wire / reference net renamed / device card adding a 4th terminal | W33, W19, W17, W18 |
| `Singular matrix` with sane topology and `0` in an `r` line | `#n` off-by-one -> 0-ohm element | W21 |
| crashes on open | document identity renamed in one place only | W22e |
| opens and simulates, every meter `0` | wire islands (W33); model name not `X<refdes>_<n>` -> W23; key/sheet mismatch -> W22 | W33, W22-W23 |
| `Too many arguments for 'r'` / `Unable to interpret '+'` | template carries clauses or ` + ` continuations | W21 |

**9. When a reference project disagrees with your tests, the tests are wrong.** A GUI-saved file
can simulate perfectly and still trip T11 (unused pin objects), T16/T17 (its legal all-purpose
template), C10 (an unreferenced card) and any name-based helper. Keep the strict checks gated on
generated files and treat the reference as the source of truth (W25).

### Validation before opening Multisim

```python
problems = b.validate()
# Checks:
# 1. Every net has ≥2 pins (no floating nets)
# 2. Every pin belongs to exactly one net
# 3. Every part's pins are inside page bounds (60 ≤ x ≤ 900, 80 ≤ y ≤ 660)
```

### Wire routing: orthogonal, junctioned, and never through a part

Generated schematics were electrically right but looked broken: buses dropped a single
straight spur from every pin, so wires ran **through component bodies** and piled up on the
same rows. A reader (and the application's own rubber-band editing) cannot recover from
that. Routing is now a first-class step, not a side effect of connecting pins.

#### The rules

| # | Rule | Why |
|---|------|-----|
| W1 | **Every segment is axis-aligned.** Never emit a diagonal; a "bend" is two segments. | editors only manipulate orthogonal wires; diagonals are unselectable and look wrong |
| W2 | **Leave a pin through an outward stub** (~14 units, perpendicular to the pin's face) before turning. | a pin sits on the symbol border; turning immediately runs back over the body |
| W3 | **Validate the stub direction, do not assume it.** A pin can be a few units from a neighbour, so try all four faces and take the first one that is actually free. | a "logical" outward direction can still be blocked |
| W4 | **Route buses in free channels** - rows/columns whose span crosses no part box - and keep one lane per net (>= 6 units apart). | two nets sharing a row look like a short and are unreadable |
| W5 | **Middle segments must avoid every part.** Only the *first* leg may touch the start part and only the *last* leg the target part. | the wire has to reach its pin, but it has no business crossing anything else |
| W6 | **Prefer L, then Z.** Try straight, then one bend, then two bends; emit the first clear candidate. | shortest readable path, and it keeps routing deterministic |
| W7 | **Score instead of giving up.** If nothing is clear, ship the fewest-crossings candidate - never an arbitrary fallback. | total failure produces the exact spaghetti we are removing |
| W8 | **A net may not carry the same two-point segment twice.** Deduplicate on `(net, min(p), max(p))`. | duplicate/zero-length wires behave like shorts and confuse the editor |
| W9 | **Junctions are explicit objects** at every T; a 2-wire corner shares ONE object. | a plain crossing does not connect; two ids at one point leave both wires dangling (W33) |
| W10 | **Give the layout corridors.** Two stages packed a few hundred units apart leave no channel, so nothing can be routed cleanly. Space parts so free rows/columns exist, and keep every part inside the safe box. | routing cannot fix geometry that has no gaps |
| W11 | **Treat every pin as an obstacle**, not just part bodies. A wire passing over another part's terminal *is* a connection, i.e. an accidental short; only the wire's own two endpoints may sit on pins. | this is what makes an innocent-looking bus read as "this resistor is wired to itself" |
| W12 | **A lane must not force a spur to wrap around its own part.** When scoring lanes, exclude the pin's own body for the *outward* direction but test an **inset** copy of it: leaving the pin exits immediately, while reaching the far side of the body passes through its core. | without the inset both sides of a resistor score identically and the wire loops around it |
| W13 | **Do not force an outward stub.** Try routes straight from the pin first; a stub is only needed when the direct routes cross the pin's own body. | always stubbing produced zig-zags next to the lane and doubled the segment count |
| W14 | **A route that starts at the stub must still draw the pin->stub leg.** If candidate paths are generated from the stub origin, prepend the pin so the first segment is emitted; otherwise the net looks routed but is open at the pin. | a resistor->base connection stopped ~18 units short of the pin: the connection existed in the file, not on the sheet |
| W15 | **Allocate exactly the junction stubs you draw, then prune the rest.** A stub is a *pin* to the netlister; one that no wire references becomes a floating node. | one unattached stub per junction -> `Warning: Singular matrix. Check node N. Ensure it is not floating with respect to net 0` -> `Simulation canceled` |
| W16 | **Never place a junction on a pin.** A pin is connected only when a wire references its `ConnectList` id; a junction sitting on the pin leaves the pin itself unwired, so that net has one terminal and the analysis dies. Offset the hub junction just outside the part and draw the short hub stub. | the supply pins and the hub pin of a two-pin net had no wire at all -> that net held one terminal -> `Singular matrix. Check node N` |
| W17 | **Never resize a part's parameter list to "clean it up".** The editor renders the *displayed* value from those slots; overwriting them makes every part show `0` while the netlist still looks fine. Point the template at the slot that already holds the value (`#2` for the stock R/V parts) and leave the slots alone. | every resistor displayed `0` although the netlist carried its real value |

#### Implementation shape (`tools/ms14build.py`)

```
part_bbox(part)            pins + the symbol's own primitives, in page coordinates
obstacles()                [(part, box)] for the whole sheet
_path_clear(pts, boxes, start_part, end_part)   per-segment obstacle test
_stub_point(part, pin)     first free outward face
_elbow(pin, net_point)     stub -> L/Z candidates -> first clear (else least bad)
connect_net(...)           bus mode: pick a lane, junction per pin x, elbow per pin
                           star mode: hub junction, elbow per spoke
_wire(...)                 dedupe on (net, endpoints), axis-aligned points only
```

#### Verifying without launching the application

`tools/preview.py` renders the sheet (parts, pins, wires, junctions) to PNG and counts
segments that cross a body they are not attached to:

```bash
python preview.py <out>.ms14 -o preview.png      # CLEAN / PROBLEM + picture
python preview.py <out>.ms14 --no-png --overlap  # list offending segments

```
<out>.ms14   parts=NN  wires=NN  joints=NN  cross=0  shorts=0  open=0  CLEAN
```

Three independent metrics, all must be zero:

| metric | meaning | symptom when non-zero |
|--------|---------|----------------------|
| `cross` | segment through a part body it is not attached to | wire looks like it goes "into" the component |
| `shorts` | segment through a foreign pin | "this resistor is wired to itself" - an accidental connection |
| `open` | wire endpoint in empty space (not a pin, junction, label, or another segment) | a net that is complete in the file but broken on screen (a connection missing its last leg) |
```

It is also part of the offline suite (T12 overlap, T13 safe box), so a layout regression
fails the same command that already gates the file-format invariants (see "Portable integrity
rules" for the format-side checks they sit next to):

```
<out1>.ms14   parts=NN  nets=NN  ports=NN  models=NN  PASS
<out2>.ms14   parts=NN  nets=NN  ports=NN  models=NN  PASS
<control>     parts=NN  nets=NN  ports=NN  models=NN  PASS
```

⚠️ The overlap metric must ignore a *legitimate* attachment: a wire ending on a pin is
inside that part's box by definition. Compare endpoints against the part's pins (tolerance
a few units) before flagging it.

#### Portable version (for any tool that emits a schematic)

1. Build a box for every placed item once, from pins *and* the item's drawn primitives.
2. Route with `stub -> L/Z -> join`, always axis-aligned, validating each segment against
   the boxes; allow only the two endpoint items to be touched.
3. Place buses in free lanes, one lane per net, and create an explicit junction object at
   every T.
4. Deduplicate emitted segments per net.
5. Render the result to an image and count body-crossing segments; assert it is zero in
   the same test run as the format checks. Screenshot-free, application-free, and it
   catches the exact defect a reviewer sees first.

### Static tests before Multisim ever opens the file

Multisim crashes on structurally broken input, so the invariants are asserted offline.
`tools/test_files.py` checks a generated file against a **known-good reference**: a project
the GUI itself saved (one ships under `<SKILL_DIR>/tools/xml/`, use any of your own):

```bash
cd tools
python test_files.py --ref <control>.xml <out1>.ms14 <out2>.ms14 -v
```

| Test | Invariant |
|------|-----------|
| T1 | every `CiComponent/Ports` entry resolves to a `CiPort` owned by that component |
| T2 | every port belongs to exactly one `CiNode`, every net has >= 2 pins |
| T3 | every `CIITPinSymbolComp` points at a port of its own component |
| T4 | every `CiComponent/Model` exists **and** is listed in `CiCircuit/Models` |
| T5 | every `CiModel` carries a SPICE card in `Attributes[1]/CiaCString` |
| T6 | every pin lands inside the page |
| T7 | no `CiID` is defined twice (references legitimately repeat) |
| T8 | *info*: drawing primitives missing the `Transformer-M*` matrix (optional - real files omit it) |
| T9 | every tag/attribute emitted also appears in the reference file |
| T10 | `CIITSymbolComp/CiComponent` resolves to a real component (synthesized-part crash) |
| T11 | `CiPort/Nodes` names exactly the `CiNode` that lists the port |
| T12 | no wire segment crosses a part body it is not attached to (rendered geometry) |
| T13 | every part sits inside the safe box *(policy: enforced for generated files only)* |
| T14 | no wire passes over a foreign pin (would read as a short) |
| T15 | no wire endpoint hangs in space (a dropped segment leaves the net open) |
| T16 | SPICE templates are netlist-safe: no inline ` + `, every `#n` slot exists |
| T17 | expanded template has the right token count for its element letter |
| T18 | every junction stub / pin placeholder is referenced by a wire (no floating pins) |
| T19 | the reference net is named `0` and carries the ground symbol |
| T20 | every part pin is referenced by a wire (no open terminals) |
| T21 | an instrument's model matches its mode (volts = high-Z, amps = near-short) |
| T22 | every `CiNode` carries the 33-group `Attributes` block, reference flag (group 16) set on net `0` only |
| T23 | an expanded `r`/`v` value is real (non-zero for `r`), and the string value equals the numeric mirror |
| T24 | every instrument key is `<refdes>#1/<sheet>:`; the sheet equals `DesignSheet/@Title`, the title equals the output file stem, `Project/@Name` and `Sheet/@SheetName` agree with it, and the refdes exists |
| T25 | every pin connection object sits at `symbol offset + connector centre` (page coordinates); a local one leaves the pin unattached |

`tools/diff_part.py` answers the narrower question "is this one part isomorphic to a part
that works?":

```bash
python diff_part.py <out>.ms14 <refdes> <control>.xml <donor-refdes>
# == component  nodes: generated=23 donor=23
# == symbol     nodes: generated=33 donor=33      <- no MISSING lines = schema-identical
# == pins       D/G/S vs C/B/E, own CiIDs
```

⚠️ A known-good control file must always pass; if the control fails, the test is wrong, not
the generated file. The generic version of these rules - written so they can be lifted into
any other skill that writes project files - is "Portable integrity rules" below. Two real bugs were found this way (see Troubleshooting): a deleted
`CiCircuit` element and un-remapped `CiPort/Component` references.

### Round-trip verification (needs Multisim installed)

```bash
# Open, auto-save, extract, compare
cd tools
powershell -File echosave.ps1 -File <out>.ms14
python ms14.py  # unpack saved version
# Multisim drops invalid elements — if counts match, file is clean
```

### Screenshot without manual interaction

```powershell
cd tools
.\shot.ps1 -File <out>.ms14 -Png <out>.png
# Launches Multisim, captures window, saves PNG (needs unlocked desktop)
```

## File format details

### Container structure

```
[36 bytes]  "MSMCompressedElectronicsWorkbenchXML"  (.ms14 magic)
[4 bytes]   total_uncompressed_size (little-endian)
[4 bytes]   padding (0)
repeat:
    [4 bytes]   block_raw_size (≤900000)
    [4 bytes]   block_compressed_size
    [N bytes]   PKWARE DCL implode block (type=1, dict=4096)
```

**Critical**: The codec is PKWARE DCL (MPQ/Diablo format), NOT zlib/deflate. Using wrong compression makes files unreadable.

### XML schema (simplified)

```
MSMElectronicsWorkbench
└─ Project
   ├─ UniqueSheets/...
   │   └─ CIITDiagram               ← the schematic
   │      ├─ Components              (drawing: symbols, wires, labels)
   │      └─ Elements                (netlist: parts, models, nets, ports)
   └─ Extensions                     (instruments, analysis settings)
```

**Netlist model** (`Elements/Item`):
- `CiComponent` — placed part (refdes, model, instance GUID)
- `CiPort` — one pin (name, net membership)
- `CiModel` — SPICE `.MODEL` or `.SUBCKT` text
- `CiNode` — net (name, member ports)
- `CiCircuit` — index of all models/nodes/components

**Drawing model** (`Components/.../Objects/Item`):
- `CIITSymbolComp` — symbol at (x,y) in 1/1000 inch
- `CIITPinSymbolComp` — pin with connector stub
- `CIITLinkComp` — wire (orthogonal polyline, endpoint refs)
- `CODNodeTextComp` — net label with back-reference to wire

## Common patterns

### RTL 3-input OR

```python
# Topology: 3-input NOR (stage 1) + inverter (stage 2)
# Stage 1: one base resistor per input into a common base, collector load R1
# Stage 2: inverter driven by the stage-1 collector, output at its collector
```

See `<SKILL_DIR>/tools/make_circuits.py` for the reference implementation.

### TTL totem-pole AND

```python
# Multi-emitter input pair sharing base+collector
# Phase splitter, totem output (pull-up + diode + pull-down), cascaded into a
# second identical stage wired as an inverter
# Level-shift diode: an NPN with base and collector tied (VBE ~= 0.7 V)
```

See `<SKILL_DIR>/tools/make_circuits.py`.

### CMOS 3-input NOR

```python
# 3 PMOS in series (pull-up), 3 NMOS in parallel (pull-down)
# Sizing: W/L(PMOS) = 3×2×W/L(NMOS) for equal rise/fall
# 6 transistors total
```

See `<SKILL_DIR>/tools/make_circuits.py`.

### Transmission-gate OR

```python
# TG = parallel NMOS+PMOS with complementary gates
# OR built from mux stages: y1 = a ? a : b, y = y1 ? y1 : c
# 6 transistors per stage (2 TG + 1 control inverter)
```

See `<SKILL_DIR>/tools/make_circuits.py`.

## Critical gotchas (learned the hard way)

1. **Joins are by object id, never by position (W33).** Two wires at one point must share one object; three or more need a junction. Position coincidence alone joins nothing. Run `wiregraph.py` first.
2. **Wire must have no transform**: `CIITLinkComp` with `Transformer-M*` attributes gets silently dropped
3. **Net label back-reference**: `CODNodeTextComp/Links` must point to its wire's ID, else wire invisible
4. **Bi-directional net membership**: `CiNode/Ports` → port IDs AND `CiPort/Nodes` → node ID, both required
5. **All IDs remapped**: Clone parts with fresh GUIDs, remap every `CiID`/`PortID`/`Connect1/2`
6. **Page bounds enforced**: parts outside (60,60)-(900,660) cause layout corruption
7. **No rotation/flip on generated parts**: only `OrientationFlip="0"` parts have simple geometry

## Part library (comprehensive native coverage)

### Built-in Multisim component library

⚠️ **Verified 0/133**: the sample `.ms14` files carry **no inline symbols** — their
`CiComponent/SymCompID` values never resolve inside any `Objects` collection. They are
useful for *database names and model strings only*, never as glyph donors. For part data
use the master database instead (see "Native component database" below); for glyphs use
`<SKILL_DIR>/tools/xml/*.xml` or synthesize with `mosfet.py`.

**Location**: `<MS_SAMPLES>` — `%PUBLIC%/Documents/National Instruments/Circuit Design Suite <ver>/samples/`

Multisim installs 133 sample files exposing **68 unique database names** (resistors,
transistors, 74-series ICs, sources). Useful for *names* only - and superseded by
the database, which also gives pin order and model cards.

#### Quick parts lookup

```python
import json
library = json.load(open("<SKILL_DIR>/tools/multisim_library.json"))
# {"<part>": {"file": "<sample>.ms14", "refdes": "&ASC<R1>", "category": ""}, ...}
```

Generate library index once:
```bash
cd tools
python << 'EOF'
import ms14, pathlib, json
samples = pathlib.Path(ms_paths()["samples"])      # see "Installation paths"
library = {}
for ms14_file in samples.rglob("*.ms14"):
    try:
        xml = ms14.unpack(str(ms14_file))
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        for comp in root.iter("CiComponent"):
            attrs = comp.find("Attributes")
            if attrs and len(attrs) > 4:
                items = list(attrs[4].iter("Item"))
                if len(items) > 1:
                    part_name = items[1].get("Value", "").replace("&ASC", "")
                    if part_name and part_name not in library:
                        library[part_name] = str(ms14_file.relative_to(samples))
    except: pass
json.dump(library, open("multisim_library.json", "w"), indent=2)
EOF
```

#### Component families found

| Category | Family names you will see |
|----------|--------------------------|
| **Analog** | `RESISTOR`, `CAPACITOR`, `INDUCTOR`, `POTENTIOMETER` |
| **Power** | `POWER_SOURCES` (VCC/GND), `SIGNAL_VOLTAGE_SOURCES` |
| **Semiconductors** | `BJT_NPN`, `BJT_PNP`, `DIODE`, `SWITCHING_DIODE`, `LED` |
| **Transistors** | `TRANSISTORS_VIRTUAL`, plus per-device families |
| **Op-Amps** | `OPAMP`, `WIDEBAND_AMPS` |
| **Digital ICs** | `74HC_2V`, `74HC_4V`, `74LS`, `74STD`, `CMOS_5V`, `TIL` |
| **Microcontrollers** | `805x`, `PIC`, `AVR` families |
| **Sources** | `SIGNAL_CURRENT_SOURCES`, `DIGITAL_SOURCES` |
| **Displays** | `HEX_DISPLAY`, `SEVEN_SEGMENT` |
| **Passive** | `TRANSFORMER`, `RPACK` (resistor array) |
| **Control** | `CONTROL_FUNCTION_BLOCKS`, `ANALOG_VIRTUAL` |
| **Misc** | `SWITCH`, `VOLTAGE_REGULATOR`, `FWB` (bridge rectifier) |

### Using native library parts

```python
import ms14build as B

# Pick donor based on part needed
samples = ms_paths()["samples"] + os.sep            # see "Installation paths"

# any sample that already contains the family you need works as a donor
pal = B.Palette(samples + "<sample>.ms14")

npn = b.add_part(pal, pal.pick("BJT_NPN"), 300, 200, "Q1")
pnp = b.add_part(pal, pal.pick("BJT_PNP"), 500, 200, "Q2")
mos = b.add_part(pal, pal.pick("TRANSISTORS_VIRTUAL"), 400, 300, "M1")
gate = b.add_part(pal, pal.pick("<ic-family>"), 300, 200, "U1")
r = b.add_part(pal, pal.pick("RESISTOR"), 300, 200, "R1", "10k")
c = b.add_part(pal, pal.pick("CAPACITOR"), 450, 200, "C1", "100n")
vdd = b.add_part(pal, pal.pick("POWER_SOURCES"), 150, 100, "VDD")
```

### Finding specific IC models

Sample files contain **placed instances** with configured models. To find a specific part (e.g., 7408 AND gate):

```python
import ms14, pathlib

samples = pathlib.Path(ms_paths()["samples"])      # see "Installation paths"

def find_part_model(part_substring):
    """Search all samples for parts containing a substring of the part name"""
    results = []
    for ms14_file in samples.rglob("*.ms14"):
        try:
            xml = ms14.unpack(str(ms14_file))
            if part_substring.upper() in xml.upper():
                import xml.etree.ElementTree as ET
                root = ET.fromstring(xml)
                for comp in root.iter("CiComponent"):
                    attrs = comp.find("Attributes")
                    if attrs and len(attrs) > 4:
                        items = list(attrs[4].iter("Item"))
                        if len(items) > 3:
                            base_part = items[3].get("Value", "").replace("&ASC", "")
                            if part_substring.upper() in base_part.upper():
                                results.append((str(ms14_file), base_part, comp.get("LocalName")))
        except: pass
    return results

# Example: find all 74-series gates
gates = find_part_model("7408")  
# Returns: [("<sample path>", "<model>", "<refdes>"), ...]
```

### Fallback: custom donor projects

If a part isn't in samples, place it once in Multisim GUI and use that project as donor:

```python
# 1. In Multisim: Place -> Component -> pick the device you need -> place -> Save As "<part>_donor.ms14"
# 2. Unpack
cd <SKILL_DIR>/tools && python -c "import ms14; open('xml/<part>_donor.xml','w').write(ms14.unpack('<MS_SAMPLES>/<part>_donor.ms14'))"
# 3. Use
pal = B.Palette("<SKILL_DIR>/tools/xml/<part>_donor.xml")
m1 = b.add_part(pal, pal.pick("<part>"), 400, 300, "M1")
```

### Legacy approach (still works)

Old donor projects in `<SKILL_DIR>/tools/xml/*.xml` (unpacked from `Multisim_old_project/*.ms14`) provide:
- `RESISTOR_VIRTUAL`, `DC_POWER`, `GROUND`, one NPN (see the file list)
- Hand-placed gates: `7402N`, `7404N`, `7408J`, `7432N`, `7486N`
- Instruments: `XMM` (multimeter), `PROBE_DIG_*`

Use when native samples lack a specific part configuration.

## Workflow for a circuit

1. **Generate**:
   ```bash
   cd <SKILL_DIR>/tools
   python bootstrap.py                 # once per machine
   python make_circuits.py             # writes <out>.ms14 next to the project root
   ```

2. **Validate** (automated):
   - Structural: parts/nets/wires counted
   - Electrical: net size ≥2, all pins connected
   - Geometric: all parts in page bounds

3. **Open in Multisim** (manual):
   - Launch the target Multisim version
   - Open the `.ms14` file
   - Run analyses: operating point, DC sweep, transient
   - Export graphs for report

4. **Verification**:
   - `Ctrl+S` in Multisim → file re-saved with Multisim's codec
   - Unpack both versions → compare part/net counts
   - If identical, generator output is clean

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| File won't open | Wrong compression codec | Never replace `pklib.py`, always use PKWARE DCL |
| Wires missing | No back-reference in net label | `Builder.connect_net()` adds this automatically |
| Part appears but unconnected | `CiPort/Nodes` missing or `CiNode/Ports` incomplete | Use `Builder` methods, don't hand-edit XML |
| Part outside visible area | Coordinates exceed page bounds | Check with `validate()` before saving |
| Meter reads 0V on live net | wire island (W33) splits the probed net, or both meter pins on same net | `wiregraph.py` first, then verify `+` and `−` resolve to different `CiNode`s |
| Dense/unreadable layout | No routing plan, random hub selection | Use `bus=` for rails, layout by signal flow (left→right) |
| **Multisim crashes on open / part count 0** | `Builder.clear()` removed the `CiCircuit` element, so `Nodes`/`Models`/`Components` were written into a detached tree and the file shipped with no circuit | `clear()` must keep the `CiCircuit` item; run `python tools/test_files.py` (T4) on every build |
| Part opens but has no pins / wires snap nowhere | `CiPort/Component` back-reference still pointed at the donor component (`Component` was missing from `ID_ATTRS`, so it was never remapped) | `ID_ATTRS` includes `Component` |
| Symbol renders as a single stray line | drawing primitives were rebuilt from scratch, dropping the `Transformer-M00..M21` matrix and `Pen-Width` | clone a primitive the GUI itself wrote and only edit its coordinates (`mosfet._redraw`) |
| **Multisim crashes only on circuits with synthesized parts (MOSFETs)** | `CIITSymbolComp/CiComponent` still pointed at the donor component: `mosfet.remap()` did not include `CiComponent`, so the symbol's owner link dangled | remap `CiComponent`, then stamp `sym[0].set("CiComponent", item.get("CiID"))` after remapping; test T10 |
| Part's pins report the wrong owner | `CiPort` ids were stamped with the new component id **before** `remap()`, which then mapped that fresh id a second time | remap the port copy first, set `Component` last |
| Palette template and placed part share CiIDs | `mosfet` allocated ids from `max(used)+1`, colliding with `Builder._id()`'s own `500000001+` counter | synthesized parts use a disjoint range (`900000000`), symbol primitives `950000000` |
| **`Singular matrix ... floating with respect to net 0`** | **Check wire islands first (W33)** - two ids at one corner leave both wires dangling; Multisim splits the net and the parts float. Then: **(C)** template `#n` reads `parameters[n]`, so `#2` returns the dummy slot and **every resistor becomes 0 ohm** (W21, T23) - `python netlist.py` must show real values; **(A)** a `CiNode` with empty `<Attributes/>` loses the group-16 reference flag (W19, T22); **(g)** BJT card declares substrate/second-base splits (`CJS`/`VJS`/`MJS`/`RBM`/`IRB`) - a 3-pin device asking for a 4th terminal (W18); **(e)** database row re-declares the CiModel name; **(b)** reference net not named `0`. The reported node number is not the culprit - `N > nets-1` proves a device-internal node. | every pin must be referenced by a wire (T20); name the ground net `0` (T19); prune unused stubs (T18); clone the 33-group `CiNode` attribute block and set the group-16 flag on net `0` only (W19, T22); make every template read `#1` (i.e. `parameters[n]` where the value lives) and keep the numeric `doubles` mirror in sync (W21, T23); declare every connection point as a positioned `CODPinComp` and index wires/pins/labels by real class, one label per net (W20); flatten every card to one `.MODEL` line (C10); fill the database row from the database (C11); regen via the generator instead of hand-patching (M7); strip BJT cards to the 22-param safe set via `bjt_card()` (W18) |
| **The file crashes Multisim the moment it loads** | the document's identity was renamed in **one** place: the sheet name is stored six times (`Project/@Name`, `Sheet/@SheetName`, `DesignSheet/@Title`, `RefDesInfoContainer/@CIR`, `RefDesInfoData/@RefDes` paths, instrument keys) and a partial rename makes the document contradict itself (W22e) | rename textually over the finished XML: `xml.replace(old_name, file_stem)`; keep the template's own identity neutral (`skeleton.xml` / `Skeleton`); test T24 |
| **`Duplicate component name found 'q1'` (warnings only) and a stage is missing** | refdes carry a section-style tail (`Q1A1`) so several parts collapse onto one element; the netlist still says `0 error(s)` (W27) | renumber as letters+digits (`Q11`, `Q12`, ...), keep net names out of the part namespace, and assert `^[A-Za-z]+[0-9]+$` |
| **Every meter reads ~0 V (fV noise) although the simulation runs** | wire islands (W33): the editor joins by id, not position. Check `wiregraph.py` first, then `multisim_netlist.py` (W34) | fix the corner/junction ids in `ms14build.py`; see the playbook |
| **The netlist check fails with `Invalid parameter name '+'`** | a multi-line model card was stored flattened (newlines lost, `+` markers kept), so SPICE reads `+` as a parameter name (W29) | re-store every card through `set_model_text()`; never clone palette template cards as-is |
| **A node reads 0 V although it is driven** | the meter is an **ammeter**: either `mode=0`, or the cloned meter part carries the ammeter subcircuit (`R_multi_meter` ~1e-5) even though the display says V - it shorts the node to its return | select the palette meter *by model* (voltmeter = `R_multi_meter` ~1e9) and set `mode=1`; test T21 |
| **Parts display `0` but the netlist has the right value** | the generator rewrote the part's parameter slots; the editor renders the symbol text from those slots | keep the slots, fix the template instead (`#2`); set the symbol text explicitly if the model name matters (`Part.set_display_value`) |
| **Simulation aborts: `Too many arguments for function 'r'` / `Unsupported mathematical function 'r'`** | the template reads its value from a slot the value is not in, so an extra token lands on the element line | emit only the clause needed (`r%p %t1 %t2 #1`) - `#1` reads `parameters[1]`, where the value already is (W21); test T17/T23 |
| **Simulation aborts: `Unable to interpret '+'` / `Unknown symbol '+'`** | the part's SPICE template is one line but contains ` + ` line-continuations (and often `#n` slots that do not exist) | rewrite the template with only the clauses needed and size the parameters to match (`Builder.set_spice_template`); test T16 |
| Wires netlist correctly but the sheet reopens with loose pins | `CiPort/Nodes` was empty: `_rebuild_node_refs()` ran at placement time, before `connect_net()` | rebuild at save time (`Builder.save()`), test T11 |

## What ships vs what is generated (copy into any skill that has build products)

A skill is only portable if the folder you hand over is **small, source-only, and able to
build itself**. Anything the toolchain compiles or downloads is a build product: it is
machine-specific, often huge, and silently rots (an `exe` built for one CPU, a dump taken
from one database version). Never ship it; ship the recipe and one command that runs it.

### The rule

| Kind | Ships? | Examples here |
|------|--------|---------------|
| source | **yes** | `ms14build.py`, `ms14.py`, `mosfet.py`, `multisim_db.py`, `make_circuits.py`, `test_files.py`, `preview.py`, `pklib.py`, `dbms/*.cpp`, `dbms/jet2tsv.py`, `dbms/build.bat`, `xml/*.xml` |
| build product | **no** | `dbms/dbq.exe`, `dbms/*.obj`, `dbms/dump/*.tsv` (~120 MB, dumped from a 241 MB database) |
| cache / scratch | **no** | `__pycache__/`, `graft/`, `*.png` renders |
| deliverable | yes, but only the intended ones | the generated `<out>.ms14` files |

⚠️ If a tool needs a build product, it must **fail with the fix in the message**, not with a
bare `FileNotFoundError`. The current wording is
`build it first: tools/dbms/build.bat (<path>)`, and callers degrade instead of crashing.

### One command bootstrap

```bash
python <SKILL_DIR>/tools/bootstrap.py           # build whatever is missing
python <SKILL_DIR>/tools/bootstrap.py --check   # report only, non-zero if incomplete
```

```
Multisim toolchain in <SKILL_DIR>/tools
dbq.exe        ok
db dump        ok
preview.py     ok
test_files.py  ok
```

`bootstrap.py` is idempotent, prints `ok`/`MISSING` per dependency, and each build step is
skipped when already satisfied:

| Step | Condition | Action |
|------|-----------|--------|
| `dbq.exe` | missing | `cmd /c dbms/build.bat` (vcvars32 + `cl`, `g++` fallback) |
| `dbms/dump/` | missing | `python dbms/jet2tsv.py` (~1 min, needs the Multisim database) |

### Degradation, not failure

`make_circuits.py` calls `db_part()` for every transistor; if the database layer is absent
it keeps the donor model and prints one line per part:

```
(db) <part> unavailable (build it first: tools/dbms/build.bat (<path>)) - keeping donor model
```

The `.ms14` files are still generated and still pass the structural suite - just with the
generic donor model instead of the real Gumpert-Poole card. That is the difference between
a skill someone can run on a clean machine and one that only works on yours.

### `.gitignore` for the above

```gitignore
# build products - rebuild with `python tools/bootstrap.py`
tools/dbms/dump/
tools/dbms/*.exe
tools/dbms/*.obj

# python
__pycache__/
*.pyc

# caches / scratch renders
tools/graft/
tools/*.png

# generated deliverables stay if they are the point of the repo
*.ms14
!<out1>.ms14
!<out2>.ms14
```

### Checklist before handing a skill to someone else

```
S1  every generated artifact is in .gitignore (exe, dump, caches, renders)
S2  one bootstrap command rebuilds them all, idempotently
S3  --check exits non-zero when something is missing (usable in CI/pre-flight)
S4  a missing artifact produces an actionable message, not a traceback
S5  the main entry point still runs (degraded) without the optional artifacts
S6  the folder you ship is small: source + docs + the intended deliverables only
S7  paths are resolved from the file's own location or env vars, never hardcoded
```

## Portable integrity rules (copy this section into any skill that writes project files)

Writing a project file that a GUI application must reopen is the same problem in every
format: **the GUI resolves graphs of back-references and crashes or silently drops data
when one edge dangles.** It never validates with a friendly error. So the rules below are
generic; the right-hand column only shows how each one appeared in `.ms14`. Copy the rules
and the checklist; swap the examples.

### The eight rules

| # | Rule | What it looked like in `.ms14` |
|---|------|--------------------------------|
| R1 | **Never delete the root object.** Clearing a document means "empty its children", not "remove its container" - children keep pointers into it and the container is what the format needs to load at all. | `Builder.clear()` removed `CiCircuit`; `Nodes`/`Models`/`Components` were written into a detached tree, the file shipped with no circuit |
| R2 | **Every reference must be remapped, not copied.** When cloning an object graph, the set of id-bearing attributes is part of the schema. A missing key means one edge silently keeps the *source* object's id. | `CiComponent` / `Component` / `PortID` / `SymCompID` / `Model` were all id refs; `Component` and `CiComponent` were left out of the remap set → symbol pointed at the donor part |
| R3 | **Remap before you stamp.** Assigning a fresh id and then running the remapper over it maps the new id a second time. | ports ended up claiming component `N+3` instead of `N` |
| R4 | **New ids must not overlap the allocator's range.** If two producers hand out ids from different starting points, they will collide. Give each producer a disjoint block. | toolchain allocated from `max(used)+1`, colliding with the writer's own `500000001+` counter |
| R5 | **Rebuild derived back-references at save time**, not when the object is created - forward links are made later by wiring. | `CiPort/Nodes` was empty on every part; real files have it 18/18 |
| R6 | **Clone primitives, do not synthesize them.** Drawing/format objects carry more than geometry: transform matrices, pen/brush state, layer numbers, hidden flags. Copy one the application itself wrote and edit only coordinates. | `CODLineComp` lost `Transformer-M00..M21` and `Pen-Width` when rebuilt from scratch |
| R7 | **A "nice" invariant may not be a real one.** Decide with a control file, not by intuition. | the transform matrix looked mandatory, but the known-good project omits it on 270/356 primitives - never the crash cause |
| R8 | **Test against a control the application saved.** If the control fails, the test is wrong. Assertions that only pass for generated files prove nothing. | the packaged donor project (GUI-saved) is the control; every test must pass on it too |
| R9 | **A missing payload is invisible to reference tests.** Links are audited easily (does the id resolve?), payloads are not - so a generator can emit a correct graph of objects that each carry nothing, pass every id/breadth test, and still be unusable. Audit **per element class**: attribute/slot counts of every instance must match a saved file. An empty container is a defect, not a default. | `CiNode` objects were written with an empty `<Attributes/>`; every id resolved, nets had >= 2 pins, netlist checked `0 error(s), 0 warning(s)`, and the simulator still died with `Singular matrix ... floating with respect to net 0` (W19) |

### Copyable checklist (adapt the names, keep the shape)

```
C1  root object exists exactly once
C2  every object's owner/parent back-reference resolves to a real object
C3  every child list referenced from the root names existing children (no stale ids)
C4  cross-links are bidirectional: A->B iff B->A   (port->net and net->port, etc.)
C5  every id is a *definition* once; reference lists repeat ids freely - only count defs
C6  every serialized attribute has a non-None value (None fails late, inside the writer)
C7  every object carries the required payload (model text, style, matrix)
C8  all coordinates fall inside the documented page/canvas
C9  tag/attribute vocabulary is a subset of what the control file uses
C10 no two producers allocate ids from the same range
C11 every model WRAPPER Item carries the CiID its components reference (inner element carries none)
C11b the net named `0` carries the reference flag in CiNode/Attributes group 16; no other net does
C12 CiCircuit/Models uses <Item CiID="..."/> structure, not <Item Value="..."/>
C12b every object carries the payload its class requires - compare attribute-group counts per
    Class against a saved file (CiComponent 47/53, CiPort 41, CiModel 3/5, CiNode 33, CiCircuit 0)
C12c a container payload is cloned from a real file, never created empty (`<Attributes/>`)
C12d every connection point is a positioned object (`CODPinComp` + CenterX/CenterY), and the index
     references wires/pins/labels by their real class, one net-label per net
```

### Reusable test harness skeleton

```python
"""Generic project-file integrity tests. No application launch.

    python tests.py --ref <control-file> <generated>...

Every check reports a code; a control file the application saved must pass all of them.
"""

def load(path):
    return parse_inner_format(path)          # unpack container -> XML/JSON tree


def elements(root):
    """Iterate *definitions* only. Wrapper objects and their payload usually repeat the
    class/tag name, so a naive tree walk counts everything twice."""
    return next(root.iter(ROOT_COLLECTION)).find(ROOT_LIST)     # e.g. Elements


def run(path, control=None):
    root, fails, info = load(path), [], []
    defs, links, payload = collect(root)      # your collectors
    ...
    # C6 first: a None attribute explodes inside the serializer, so catch it here
    for el in walk(root):
        for k, v in el.attrib.items():
            if v is None:
                fails.append("C6 %s@%s is None" % (k, el.tag))

    # C5: definitions only
    seen = {}
    for el in definitions(root):
        seen[el_id] = seen.get(el_id, 0) + 1
    fails += ["C5 %s defined %d times" % (k, n) for k, n in seen.items() if n > 1]

    # C9: vocabulary must be a subset of the control file's
    if control:
        tags, attrs = vocabulary(control)
        info += ["C9 unknown %s" % el.tag for el in walk(root) if el.tag not in tags]

    return report(path, fails, info)
```

### Why this ordering matters

1. **C1/C2 before everything else.** A detached root makes every later check pass
   vacuously in memory and fail only on disk - or not fail at all, and crash the GUI.
2. **C6 before serialization.** `None` attributes raise inside `ElementTree`/`json` with a
   stack trace that names no object; assert it explicitly instead.
3. **C5 last.** Duplicate-id counts are polluted by reference lists; get the definition
   set right first or the output is noise.
4. **C9 is advisory.** It finds vocabulary you invented that the application has never
   parsed - useful, but the control file's own omissions mean it cannot be a hard gate.

### Mapping: `tools/test_files.py` checks -> generic rules

| Test | Enforces | Rule |
|------|----------|------|
| T1 | every `CiComponent/Ports` entry resolves to a port owned by that component | C2, C3 |
| T2 | one net per port, every net has >= 2 pins | C4 |
| T3 | every symbol pin points at a port of its own component | C2 |
| T4 | `CiComponent/Model` exists **and** is listed in `CiCircuit/Models` | C3 |
| T5 | every model carries a non-empty payload (SPICE card) | C7 |
| T6 | every pin lands inside the page | C8 |
| T7 | no id is *defined* twice (references repeat freely) | C5 |
| T8 | primitives carry the transform matrix *(info only - see R7)* | C7, C9 |
| T9 | emitted tag/attribute vocabulary is a subset of the control file | C9 |
| T10 | `CIITSymbolComp/CiComponent` resolves | C2 |
| T11 | `CiPort/Nodes` is exactly the node that lists the port | C4, C5 |

### Applying it to a new skill

1. Write `<skill>/tools/test_files.py` from the skeleton above; add one check per rule
   that your format actually has.
2. Keep a **control file** committed next to the tool - something the application itself
   saved. Never generate the control.
3. Add a one-line probe for any rule you hit, e.g. `dangling = sum(1 for s in symbols if
   s.owner not in components)`; a stable count of 0 is what you want in the report.
4. When a bug appears, add the assertion **before** fixing it, confirm it fails, then fix.
5. Record the bug in the troubleshooting table as: symptom -> root cause -> rule number.

## Integration with agent workflow

When user requests Multisim work:

1. **Read this skill** at task start
2. **Check tools exist**: `<SKILL_DIR>/tools/*.py` (or `<PROJECT>/tools/`)
3. **Load reference**: `make_circuits.py` shows working examples
4. **Build incrementally**: place parts → wire nets → validate → save
5. **Never guess structure**: clone from donor, measure from real files
6. **Report validation**: always show `validate()` output before claiming success
7. **Run the offline suite** (`tools/test_files.py --ref <control> <file>`) before handing a
   file to the user; a GUI crash is not an acceptable way to find a dangling reference

## Output format

When generating circuits, report:
```
<out1>.ms14   parts=NN  nets=NN  wires=NN  OK
<out2>.ms14   parts=NN  nets=NN  wires=NN  OK
```

Problems format:
```
! Pin R1.1 outside page bounds (x=1200 > 900)
! Net VCC has only 1 pin (need ≥2)
! Pin <refdes>.<pin> not in any net
```

## Success criteria

- `validate()` returns empty list **and** `tools/test_files.py` passes with `--ref <control>`
- the control file itself passes the same suite (otherwise the suite is wrong)
- Multisim opens file without errors
- `Ctrl+S` round-trip preserves part/net/wire counts
- Screenshot shows expected topology
- Analyses (DC/transient) produce plausible results

## References

- Full format spec: `Multisim-skill.md` (comprehensive reverse-engineering notes)
- Plan notes: `<PROJECT>/PLAN.md` (requirements, topology, analysis)
- Working generators: `<SKILL_DIR>/tools/make_circuits.py` (reference implementations)

---

**Mode**: persistent for all Multisim tasks. Load at session start when working with .ms14 files.

## Native component database (master library) — read this first for part data

The database is **not** the template file the GUI reads: it is the real library, and it
**is** readable. Part names, pin names/order, pin families, SPICE instance templates and
the full `.MODEL`/`.SUBCKT` cards all come out of it. Use the database for electrical
truth; use a project only for glyph geometry (see "Symbols" below).

### Where the databases live

| DB | Path | Size | Parts |
|----|------|------|-------|
| master | `<MS_DATA>/database/MSCOMP_*.PRD` | ~240 MB | 57,162 |
| corporate | `<MS_DATA>/database/CPCOMP_*.PRJ` | ~570 KB | site parts |
| user | `<MS_USER>/database/UsrComp_*.usr` | ~530 KB | user parts (empty by default) |
| template | `<MS_HOME>/database/UsrCompTemplate_*.usr` | ~530 KB | empty seed, **not** the library |

File names carry an edition letter (`MSCOMP_S.PRD`, `CPCOMP_S.PRJ`, `UsrComp_S_PC.usr`), so
glob on `SYS`-style patterns — never on the literal name; the letter changes between
single-user / education / professional installs.

⚠️ The master DB lives under `%ProgramData%`, **not** in the install folder. Looking only
in `Program Files` finds the empty template and leads to the wrong conclusion.

### Format, and why three readers fail

All of them are **Jet 3 (Access 97)**: `Standard Jet DB` at offset 4, version byte `0x00`
at offset `0x14`.

| Reader | Result |
|--------|--------|
| ACE ODBC (`Microsoft Access Driver (*.mdb, *.accdb)`, 64-bit) | `Cannot open a database created with a previous version` |
| Jet 4.0 ODBC (`Microsoft Access Driver (*.mdb)`, 32-bit, `msjet40.dll` present) | `Not a valid password` — even for the empty template, so it is a **version** refusal, not a password |
| Patch header `0x14: 0x00 -> 0x01`, then ACE / Jet 4 | still refused |
| **`access_parser` (pure-Python Jet page walker)** | reads everything |

So: **do not chase ODBC/ADO for this file.** The one-time bridge is Python.

### Toolchain (dump once in Python, query forever in C++)

```
<SKILL_DIR>/tools/dbms/jet2tsv.py   Jet -> TSV dump   (~59 s, needs access_parser)   # once
<SKILL_DIR>/tools/dbms/dump/*.tsv   the dump          (~120 MB, 8 tables)
<SKILL_DIR>/tools/dbms/dbq.cpp      C++ query tool    (~0.44 s per call, loads TSV in memory)
<SKILL_DIR>/tools/dbms/dbdump.cpp   ODBC variant      (kept for real Jet 4/Access 2000+ files)
<SKILL_DIR>/tools/dbms/build.bat    vcvars32 + cl, g++ fallback
<SKILL_DIR>/tools/multisim_db.py    Python API over dbq.exe (cached, no parser at runtime)
```

```bash
# once, and again only after a Multisim database upgrade
cd <SKILL_DIR>/tools/dbms && python jet2tsv.py         # arg 1 = DB path, default = discovered
cmd //c build.bat                                      # -> dbq.exe (x86; plain C++, g++ works)
python <SKILL_DIR>/tools/multisim_db.py where          # verify discovery + dump

./dbq.exe search <part> 5             # name / pin count / family / function
./dbq.exe show   <part>               # full record + SPICE card
./dbq.exe json   <part>               # machine-readable (what multisim_db.py uses)
./dbq.exe fam                         # Family_ID -> name, group, refdes template
```

```python
import multisim_db as D
D.search("<part>")        # [(name, {pins, family, function}), ...]
p = D.part("<part>")      # {'pinout': [<pins in DB order>], 'template': '...', 'spice': '.MODEL ...'}
D.pins("<part>")          # database pin order - read it, never assume
D.families()              # {'18': {'name': 'BJT_NPN', 'group': '12', 'template': 'Q%d'}, ...}
```

### Schema that matters (8 of 76 tables)

| Table | Rows | Use |
|-------|------|-----|
| `SYS_COMPONENT` | 57,162 | `Component_ID, Family_ID, Component_Name, Pin_Number, Pinout, Pin_Group, Pin_Type, Pin_Family, Kind_ID, Manufacturer, Description, Function` |
| `SYS_CONFIGURATION` | 232 | `Family_ID -> Family_Name, Family_Group_ID, Template` (refdes `Q%d`, `U%d`, `R%d`) |
| `SYS_CONFIGURATION_GROUPS` | 20 | family groups (top of the Place-Component tree) |
| `SYS_MAPPING_COMP_MODEL` | 125,936 | `Component_ID -> Model_ID` **+ SPICE instance `Template`** |
| `SYS_MODEL` | 45,419 | `MODEL_ID -> DATA` = the real model card text |
| `SYS_MAPPING_COMP_SYMBOL` | 114,319 | `Component_ID -> Symbol_ID_ANSI/DIN, Pinout_ANSI/DIN` |
| `SYS_SYMBOL_PICTURE` | 3,551 | `Symbol_ID -> Image` (compressed drawing, see warning) |
| `SYS_KIND` | 3 | `0 All`, `1 Component`, `2 Subcomponent` |

### Instance template syntax

`SYS_MAPPING_COMP_MODEL.Template` is the netlist line Multisim writes, `%`-escaped:

| Token | Meaning | Example |
|-------|---------|---------|
| `%p` | refdes | `<refdes>` |
| `%t<pin>` | pin node, e.g. `%tC` | `%tA %tK` |
| `%m` | model name | `<model>` |
| `%S0`, `%S1` | extra instance params | MOS bulk/area |

```
d%p %tA %tK %m                       diode
q%p %tC %tB %tE %m                   BJT
m%p %tD %tG %tS %tS %m %S0           MOSFET (bulk tied to source)
x%p %tD %tG %tS %m                   subcircuit-based device
v%p %t1 %t2 dc #1 ac #3 #5           DC source (see the slot warning below)
```

#### Template expansion rules (why a simulation fails with "Unable to interpret '+'")

Multisim stores the instance template as **one line** and writes it into the netlist
verbatim, substituting tokens. Two failure modes follow, both silent until you simulate:

| Rule | Consequence if broken |
|------|----------------------|
| ` + ` inside the template is SPICE **line continuation**. It only works at the start of a physical line, which a single-line template never has. | netlist gets a bare `+` → `Error: RefDes 'vdd' ... Unable to interpret '+' in expression` / `Unknown symbol '+'` |
| `#n` addresses **`parameters[n]`** - an OFFSET-BY-ONE from what it looks like: `#1` is the **second** entry, because slot 0 is a dummy. Proven by every GUI-saved part: the donor's R1 displays 200k and stores it at `parameters[1]` while its stock template reads `#1`; the a GUI-saved project does the same with 10k. Every slot used must exist. | read one slot too far and the element gets `0` - a **0-ohm resistor divides by zero and the matrix goes singular** while the netlist still validates `0 error(s), 0 warning(s)` (W21) |

The stock source part ships an all-purpose template:

```
v%p %t1 %t2 dc #1 ac #3 #5 +           distof1 #7 #9 +           distof2 #11 #13
                            ^ continuation inside one line        ^ and again
```

A DC source needs one clause, so the generator rewrites it (`Builder.set_spice_template`):

```python
part = b.add_part(pal, pal.pick("DC_POWER"), x, y, "VDD", "5")
b.set_spice_template(part, "v%p %t1 %t2 dc #1", [5])   # -> vVDD VDD 0 dc 5
```

#### The reference net must be named `0`

Every shipped sample names the ground net **`0`** (`LocalName="&ASC0"`, i.e. the string
`0`), and SPICE anchors the matrix at node 0. Name it `GND` and the circuit is electrically
fine but **nothing is tied to node 0** - the entire network floats:

```
Warning: Singular matrix. Check node 7. Ensure it is not floating with respect to net 0
Simulation canceled
```

⚠️ The reported node number is wherever the solver gave up, **not** the net with the
problem. A "floating node N" message with a plausible-looking netlist almost always means
the reference is wrong, not that node N is special.

```python
# wrong: perfectly readable, never solves
b.connect_net("GND", [...])     # -> nets: VCC, GND, A, B, C ...
# right: matches the samples and the simulator
b.connect_net("0", [...])       # -> nets: VCC, 0, A, B, C ...
```

```python
# tools/netlist.py prints exactly what the simulator will see
vVCC VCC 0 dc 5
q<refdes> <c> <b> 0 <model>   # the '0' is the anchor; 'GND' here would float everything
```

Check with T19: the net named `0` must exist and must carry at least the ground symbol
plus one return. Names are stored string-encoded (`&ASC0` == `0`), so strip the `&ASC` /
`&UNI` prefixes before comparing.

#### Placement: put the instrument where it measures

Fixed instrument coordinates are a trap: as the layout changes the symbol drifts away from
its node, ends up sitting on a wire, or hangs outside the sheet - and the editor may also
restore instrument positions from the user's profile, which makes a correct file *look*
wrong. Anchor the instrument to the pin it probes and put it where there is guaranteed
space:

```python
px, py = target_part.pin_pos(target_pin)          # the node to measure
band = max(box_bottom for every part) + 8          # free strip below the circuit
# try x offsets around px, keep the first candidate whose body hits no part and
# stays inside the sheet, then place the meter there
```

Rules:

1. **Anchor to the pin, don't hardcode (x, y).** The meter then stays next to what it reads.
2. **Search the candidates**, do not assume: the first free spot around the pin, inside the
   safe box and clear of every other body. A meter dropped on a resistor hides it and looks
   like the part moved.
3. **Prefer the free band** below (or beside) the parts - it is always empty, so both meters
   land in a predictable place instead of inside the routing.
4. **Both terminals must reach their nets** (see T20): pin 1 to the node, pin 2 to `0`.
5. **Leave room for the whole symbol, pins included.** The XMM body is 45..84 from its
   origin but the pins exit at **93**, and the reference label sits at 27. Size the free
   band from the symbol's *full* extent, then route the return rail **below the pins** - a
   meter placed at `safe_bottom - 97` leaves its pins at the page edge and the ground rail
   it forces down lands off-sheet (the drawing then shows meters hanging off the bottom).
6. **Pin 1 is the left pin, pin 2 the right one - so a probe lead must not cross the
   return lead.** A node wire that has to leave to the right runs over pin 2's own stub to
   the rail and reads as a short across the meter. Either put the meter to the right of the
   node's bus lane (pass the lane as a placement hint) or let the router treat the meter's
   other lead as an obstacle (`_meter_segs`); do both, they catch different layouts.
7. **Route the rails first.** Net `0` owns both meter returns, so drawing it before the
   `+` leads gives the router those wires to avoid instead of the other way round.
8. If a symbol still appears detached when the file is opened, check whether the editor
   restored instrument window positions from the profile; the geometry in the file
   (symbol `Transformer-M20/M21`) is what regeneration controls.

Verify with the renderer and the two meter checks:

```bash
python preview.py <out>.ms14 -o preview.png      # cross / shorts / open / stack
python checkmeters.py <out>.ms14                # bbox, lead direction, rail below
python checkmeterroles.py <out>.ms14            # XMM1 + -> Y, - -> 0, ...
```

**Wire-vs-wire is part of routing, not just cosmetics.** A wire that crosses a *foreign*
pin is excluded already, but a wire whose endpoint lands in the middle of another net's
wire is joined to it by the editor's junction - the same silent short as two nets meeting
at a coordinate point. `_elbow` therefore scores `(body violations, wire conflicts)` in
that order, and `checknets.py` asserts no point is shared by two nets.

#### Reading 0 V on every meter

The dial text is **stored in the file**, not measured: `NI_EWB_CURRENTDISPLAYDATA_VALUE` holds
the last reading as a string (`&ASC19.725 mV` in a real saved project, `&ASC0` right after
generation). Press **Run** once - the value only changes then. If it *stays* 0 V after a run
the sheet does not simulate: the drawing is fine (geometry lives in `Objects`, which is why
the picture looks perfect) but the simulator nets nothing. Check with `checksim.py`, which
encodes C1-C8 below. The three causes seen so far, in the order they bite:

1. **Circuit membership must resolve.** `CiComponent/@Circuit`, `CiNode/@Circuit` and
   `CiModel/@Scope` all carry the id of the sheet's **single** `CiCircuit`. Remapping those
   attributes like object ids gives every part its own nonexistent circuit - so nothing is
   simulated. Real files: one id, everywhere (`48598440` in the donor, on all 9 components
   and all 4 models).
2. **Names are `&ASC`-encoded.** Every GUI-saved file stores `LocalName="&ASC0"` for the net
   whose name is `0`. A bare `LocalName="XMM1"` is a *different* string, and an instrument's
   `CSourceSymbolCollectNode` key is `&ASC<refdes>#1/Project:` - so a bare name leaves that
   block unbound and the meter has no measurement mode or probed node.
3. **No dangling ids, no duplicate model names.** `CiCircuit/Components|Models|Nodes` list
   only the live objects of that class (a model filed under `Components` or a pruned model
   still listed is a broken reference), and two `CiModel`s sharing one LocalName make the
   subckt name ambiguous - a voltmeter can resolve to the ammeter card (10 uOhm across its
   terminals) and read 0 V regardless of its A/V button. Cloning a part for its glyph brings
   its own card, so borrowing another leaves an orphan behind: prune, dedupe, then rebuild
   the lists from the element table.

Plus one netlist-expansion trap: a meter's template is `%p %t1 %t2 %m` with no leading
letter - the letter comes from the refdes (`XMM1` starts with `X`, i.e. a subcircuit call),
and `%m` is the name **declared inside the card** (`.subckt XMM1_V`, or `Q2N3904/ON` for a
`.model` card), never the CiModel's LocalName. A checker that requires a literal letter in
the template drops every meter, so `V(X)` is never verified.

Sanity sources: `checksim.py` must say `SIMULATABLE`, the expanded netlist must list both
meters with distinct node pairs (`XMM2 X 0 XMM2_V`), and `netlist.py --check` must report no
dangling node.

#### Junction dots and doubled wires

A rail is drawn as *segments between junctions*, one junction object per tap. Two rules
decide whether the drawing is clean, and both are checked by `checkjoins.py`:

1. **A dot means a T, nothing else.** A junction object with only two attached wire ends is
   a corner drawn with a dot - it reads as a connection that is not there, and users call
   them "extra joins". Only allocate the object when three or more wire ends meet.
2. **No two wires may cover the same stretch.** A spur that arrives *collinear* with the
   bus is drawn on top of the bus segment between two junctions, and a trunk laid over an
   existing wire doubles it. Both look like a doubled rail and merge unpredictably when the
   schematic is edited. `_elbow` therefore rejects any leg that runs along the bus line, and
   `_free_lane` / `_free_column` refuse a lane that overlaps an existing wire.

The layout rule behind most doubled wires: **pins stacked in one column cannot each drop
straight down.** The lower pins sit inside the bodies below them, so every spur ends up in
the same free channel and they all overlap. Give such a group one *shared trunk* in a free
adjacent column, with a tap per pin (that is `_trunk`). On a vertical bus the mirror case is
a row of pins on the bus's own row: chain them end to end (`_chain`), never two leads.

Corollary for star nets: three or more spokes around one hub overlap as soon as two share a
column, so a net with more than two pins is routed as a bus instead of a star.

#### Instruments: right quantity, right polarity, right node

A multimeter is a *component in the circuit*, not an annotation. Three things must line up:

| Aspect | Correct | Consequence if wrong |
|--------|---------|---------------------|
| quantity | `mode=1` = volts, `mode=0` = amps **and** the matching model | an **ammeter wired across a node is a short**: it clamps the node to its return (0 V) and the schematic then contradicts the netlist |
| model | voltmeter subcircuit has `R_multi_meter` ~`1e9`, ammeter ~`1e-5` | the display setting does **not** change the loading: a meter showing "V" but carrying the ammeter card still shorts the node and reads 0 V |
| polarity | pin **1 = +** to the measured node, pin **2 = return** | reading comes out negative and reads like a stuck node |
| node | probe the node you actually want to report | a meter on the wrong net is worse than no meter: it looks authoritative |

Confirm the mode in the saved file - the value lives in the instrument data, not the symbol:

```
CSourceSymbolCollectNode/@CompLongName = &ASCXMM1#1/Project:
  NI_EWB_MEASUREMENT_MODE = 1     # 1 = volts, 0 = amps
  NI_EWB_SIGNAL_MODE      = 1     # DC
```

A quick sanity source: in a project that was simulated, mode-0 meters display `uA`/`mA`
values and mode-1 meters display `mV`/`V` values - the displayed unit tells you which mode
the part is in.

The instrument's **model** decides the loading, and it is separate from the A/V button:

```
.subckt XXMMx_... 2 1
  I_multi_meter 1 2 DC 0
  R_multi_meter 2 1 1.000000e-005      <-- ammeter: 10 uOhm across the terminals
.ends
```

so a meter that *displays* V but carries that card is a short across the node: the reading
is `0 V` for any circuit, and the node it probes is pulled to its return. Pick the palette
part by model, not by name: the ammeter and voltmeter are the same `XMM` symbol with
different subcircuits (one donor project shipped two ammeters and one voltmeter). Test T21
checks `R_multi_meter` against the requested mode.

#### Nodes must be solvable, not just connected

A netlist can pass the checker and still not solve: every node needs a **DC path to
ground through a non-infinite element**. Start with the most common cause, W19 below -
a net object that carries no payload at all.

- **A `CiNode` with an empty `<Attributes/>` block (W19).** The netlist syntax is fine and
every id resolves, but the reference flag the simulator reads lives in that block. This is
the one defect that survives all of T1-T21: those tests check *references*, and this is a
*missing payload*. Symptom: `0 error(s), 0 warning(s)` for the netlist, then
`Singular matrix ... floating with respect to net 0 (ground)` on whatever node the solver
reaches first.
- **Unattached pin objects.** Junction stubs are pins. Allocating `spins + 2` per junction
  and then drawing fewer wires leaves floating pins; the run dies with
  `Singular matrix ... Check node N ... floating with respect to net 0 (ground)`.
  Fix: size the stub list from what will be drawn, then prune whatever ends up unused at
  save time.
- **A pin with no wire is invisible to the netlister.** Connectivity is resolved from
  wire `Connect` ids, *not* from the CiNode/Port bookkeeping a generator keeps for itself.
  `tools/netlist.py` believed a resistor pin joined a transistor base, but neither pin had a wire
  in the file - so the simulator saw a one-terminal node. Dump it:
  `pin ConnectList id + wire Connect1/Connect2` and diff the two sets (test T20).
- **Instruments do not conduct.** A voltmeter is an ideal open (a 0 A source), so it never
  ties a node to ground. A node that exists only because a meter probes it will be
  singular; make sure something real (resistor, source, transistor channel) connects it.

Static check: expand the templates, count element terminals per node, and require >= 2
(`tools/netlist.py --check`, test T18 + node list). A node listing such as

```
<out>.ms14   elements=NN  nodes=NN  dangling=0
   <net1>   4 terminal(s)   <net2>   2 terminal(s)   <net3>   2 terminal(s)
```

is the shape you want: nothing with one terminal, ground with the most.

#### A net's name comes from its label, not from its CiNode (W17)

The project skeleton ships a `CDesignNetContainer` with **net-label objects** named `VCC` and
`GND`. They are not decoration: Multisim takes a net's *name* from them. Leave them behind and
the ground net stops being called `0`. The two messages arrive together:

```
Warning: No ground node was found in your circuit. To ensure accurate simulation,
         add a ground component and simulate again.
======= SPICE Netlist check completed, 0 error(s), 1 warning(s) =======
Warning: Singular matrix. Check node 3. Ensure it is not floating with respect to net 0
Simulation canceled
```

With no reference node **every** node floats, so the reported node is just the first one the
solver meets. It therefore moves with the size of the schematic - `node 3` for a
source+resistor, `node 14` for a nine-net gate - and looks like a fresh connectivity bug on
each run. That wander is the signature; chase it and you will "fix" the wrong thing forever.

Note the netlist check above says **0 errors, 0 warnings** about the `Singular matrix`: the
`No ground node` warning is the one that matters, and it scrolls off the top.

Rules:

- **Purge the template's labels in `clear()`** - empty `Project/.../CDesignNetContainer/NetLabels`.
  `ms14build.Builder.clear()` now does this.
- **A label must never name a net that does not exist on the sheet.** Real decks do carry stale
  labels (`CustomComparator` keeps `A0`..`A3`, `HW3` keeps child-sheet names like `HB1/A0`), so
  the *only* calibrated rule is the ground one: a label called `GND` requires a net called `GND`.
  `checksim.py` **C12**. It fires on none of the 18 genuine Multisim decks on this machine, and
  on the defect above.
- Do **not** require a net literally called `0`: `Error.ms14` names its ground net `GND` and
  works. A check that demands `0` rejects 17 of 18 real decks.

#### A 3-pin transistor must not ask for a 4th terminal (W18)

`node N` in `Singular matrix. Check node N` can be *arithmetically* ruled out as a wire:

- the drawing has 9 nets, so the solver numbers them `0..8`;
- each BJT with `RC`/`RB`/`RE` adds 3 internal nodes, 2 BJTs -> 6 more -> `0..14`;
- the reported node was **14**.

`14 > 8`, so it is a device-internal node, not a net - which is why rewiring, junction
dots and net labels all "fixed" nothing. The database hands out MODPEX cards that also
carry:

| parameter | what it asks the solver to build |
|---|---|
| `CJS`, `VJS`, `MJS` | a collector-**substrate** junction → a 4th terminal. At DC it has only a capacitance to ground, so the node has no conductive path at all. |
| `RBM`, `IRB` | a second base-resistance split → an extra internal base node |

Fix: emit only the parameters a 3-pin device can honour. `make_circuits.bjt_card()` filters
a database card down to the set that **provably simulates in this Multisim build** - the 22
parameters of the donor's referenced 2N2222A card:

```
IS NF BF IKF VAF ISE NE NR BR IKR VAR ISC NC RB RE RC CJC MJC VJC CJE TF TR
```

Rules:

- Keep `RB`/`RE`/`RC` - the working donor card has them, so they are safe; they add
  internal nodes that are *always* connected.
- Drop `CJS`/`VJS`/`MJS`/`RBM`/`IRB` always.
- Do not chase the node number as a wire. Convert it: `(number - (nets-1))` tells you how
  many internal nodes the solver is building beyond your schematic.

`checksim.py` **C14** fails a *referenced* BJT card that declares one of those five. It is
silent on this machine's genuine decks, which do contain such a card but never reference it.

#### A net object with no payload is not a net (W19)

This is the trap that costs the most time, because **every structural test passes**: ids
resolve, nets have >= 2 pins, wires touch pins, the SPICE netlist checker prints
`0 error(s), 0 warning(s)` - and the run still cancels with

```
Warning: Singular matrix. Check node 4. Ensure it is not floating with respect to net 0 (ground)
Simulation canceled
```

The node number is meaningless: with no reference node **nothing** is anchored, so the
solver fails wherever it happens to start. On the same broken file it was node 14 for the
full gate and node 4 for a 7-part slice - a number that tracks the size of the schematic,
not a wire.

##### The defect

```xml
<!-- generated: an element exists, but it carries nothing -->
<Item CiID="500000444" Class="CiNode">
  <CiNode Class="CiNode" LocalName="&ASC0" Circuit="212316656">
    <Attributes/>          <!-- EMPTY: 0 groups -->
    <Ports>...</Ports>
  </CiNode>
</Item>
```

A GUI-saved net carries a **33-group `Attributes` block**, and **group 16 (0-based) holds
the reference flag** - one `CiaDOUBLE` item on the net named `0`, empty on every signal net:

```xml
<!-- real file (reference.ms14, xml/Electronics1.xml, any GUI save) -->
<Attributes>
  <Item/> ... <Item><CiaParamList Class="CiaParamList"/></Item> ...
  <Item><CiaDOUBLE Class="CiaDOUBLE"/></Item>   <!-- group 16, ground only -->
  ... 33 groups total
</Attributes>
```

Verified against the ground truth: a GUI-saved project that simulates perfectly
flags **only** its two `0` nodes; nodes `1..8` are unflagged. The shipped donor
(`xml/Electronics1.xml`) does exactly the same on `&ASC0` and on none of `&ASC1..&ASC6`.

##### The rule

**Clone the payload; never synthesize it.** A net object is written as: take a
33-group `Attributes` block from a file the application saved, clear group 16, and set
group 16 to a single `CiaDOUBLE` **iff the net is named `0`**.

```python
# ms14build.Builder - correct
n.append(self._node_attrs(key))      # 33 groups cloned from the skeleton/donor
...
def _node_attrs(self, key):
    attrs = copy.deepcopy(self.node_attrs_proto)          # never a fresh ET.Element
    g = list(attrs)[16]                                   # the reference flag
    for c in list(g):
        g.remove(c)
    if key == "0":                                        # only ground
        ET.SubElement(g, "Item").set("Class", "CiaDOUBLE")
    return attrs

# WRONG - what produced the singular matrix
t n.append(ET.Element("Attributes"))     # a plausible-looking empty block
```

##### Finding it: element-type parity

You do not have to guess which element type is short a payload. For each `Class`, count the
attribute groups per instance and compare the file against a GUI-saved one; a generator bug
shows up as a **single class whose count collapses to 0** while every other class matches:

```bash
python - <<'EOF'
import ms14, xml.etree.ElementTree as ET
for p in ('../<out>.ms14', '../reference.ms14'):          # broken next to known-good
    dia = next(ET.fromstring(ms14.unpack(p)).iter("CIITDiagram"))
    for cls in ("CiComponent", "CiPort", "CiModel", "CiNode", "CiCircuit"):
        g = [len(list(it[0].find("Attributes"))) if it[0].find("Attributes") is not None else None
             for it in dia.find("Elements") if it.get("Class") == cls]
        print(p.split('/')[-1], cls, sorted(set(g)))
EOF
```

```
reference.ms14       CiComponent [47, 53]   CiPort [41]   CiModel [3, 5]   CiNode [33]   CiCircuit [0]
<out>.ms14          CiComponent [47, 53]   CiPort [41]   CiModel [3, 5]   CiNode [0]  <-- defect
```

Everything matching except one class is the whole diagnosis. `CiCircuit` legitimately has
0 groups; treat the counts as a fingerprint per element class, not a global rule.

##### Second opinion from the GUI itself

`Spreadsheet View -> Nets` on the broken sheet listed **one net per pin** (14 nets for a
7-part slice: `0..13`) even though the file declared 5 nets. That is what "no reference
node" looks like from the outside - the application could not group pins into nets at all,
while the schematic still drew perfectly. Use it as a cross-check, not a substitute for
the parity check.

##### Guard

Test **T22** asserts, for every net: 33 attribute groups, group 16 set on `0` and only on
`0`. It is silent on `reference.ms14` and on the donor, and it fails loudly on the pre-fix
generator output - which is exactly the shape a regression guard must have.

##### Why the other suspects were innocent (recorded so they are not re-chased)

Each of these was eliminated by direct comparison against `reference.ms14`, which simulates:

| Suspect | Evidence it was innocent |
|---|---|
| Model cards | a GUI-saved project *does* use multi-line MODPEX cards with ` + ` continuations (`NPN(Is=6.734f ... +`) and simulates. `+` is legal in the application's own netlist. |
| Net membership / topology | nets are **1:1 identical** to the reference after role-mapping the refdes (`{Q.C, Rb.1, Rc.1, XMM.1}` etc.). Same pin and net counts, `dangling=0`. |
| Component payloads | all attribute groups of every transistor, instrument, source and resistor are value-identical to the reference's. |
| Port objects | `CiPort` = 41 groups in both; `CiPort/Nodes` and `CiNode/Ports` agree in both. |
| Wiring geometry | WITHDRAWN: position coincidence passed while the editor saw islands. Geometry checks cannot prove joins; only shared ids do (W33). |
| Net names | a GUI-saved project usually leaves nets auto-numbered; a generator names them. Naming is not the fault - a missing *payload* is, whatever the name. |
| Junction stubs / labels | WITHDRAWN: stub checks passed while corners used two ids at one point. Use `wiregraph.py` (W33). |

Lesson (updated): when a file passes every reference test and still refuses to solve, audit **joins by shared id first** (`wiregraph.py`, W33), then payloads per element class (R7/C7). Position coincidence is not a join.

#### The reference sheet's connectivity index (W20, superseded by W33)

Old claim (wrong): the sheet joins points by coordinate, so every `CODPinComp` needed a payload position. Verified fix (W33): the editor joins by shared object id. Positions still matter for drawing, but two objects at the same coordinates are NOT joined. Keep the payload code (`_ref_pin` with CenterX/CenterY) because genuine sheets carry it, but a connectivity bug is a shared-id bug first: run `wiregraph.py` before auditing positions.

Kept mechanics: reference objects by real class (wires `CIITLinkComp`, pins `CIITPinConnectorComp`, labels `CODNodeTextComp`, only connection points `CODPinComp`); one net-label object per NET.

#### `#n` is `parameters[n]`, and a wrong slot is a singular matrix (W21)

This is the quietest possible way to break a circuit: **the netlist validates, and the matrix is
singular.** The template slot index is offset by one, so a template that *looks* right reads a slot
that holds `0`:

```python
b.set_spice_template(part, "r%p %t1 %t2 #2")   # WRONG: #2 is parameters[2] == "0"
b.set_spice_template(part, "r%p %t1 %t2 #1")   # right:  #1 is parameters[1] == "10k"
```

```
rRa A N1 0        <- what Multisim netlists from #2: a ZERO-OHM resistor
1/0 -> the solver has no finite conductance -> "Singular matrix. Check node N"
```

The proofs, both from files the GUI itself saved:

| source | shown in the sheet | stored at | its template reads |
|--------|--------------------|-----------|--------------------|
| `xml/Electronics1.xml` R1 | `200k` | `parameters[1]` | `#1` |
| `xml/Electronics1.xml` V1 | `8.7` | `parameters[1]` | `#1` |
| `reference.ms14` R1 | `10k` | `parameters[1]` | `#1` |
| `reference.ms14` V1 | `5` | `parameters[1]` | `#1` |

So: **`#n` = `parameters[n]`**, slot 0 is a dummy, and the stock templates are already correct -
the "fix" of bumping the index is the bug.

Two more traps sit in the same group, and they must agree with the string list:

- **The numeric mirror.** A part carries `parameters` (strings) *and* a `doubles` list. Writing only
  the strings leaves a clone running at the **donor's** value - a 5 V source that still says 8.7 V.
  Write both (see `Builder._set_value`).
- **The displayed value.** The editor renders the value from these lists, so a wrong slot also shows
  `0` in the schematic (`W17` corollary: never resize the list, fix the template).

Guards: **T16** (`#n` must exist: `0 <= n < len(parameters)`), **T17** (expanded token count per
element letter), **T23** (an expanded `r`/`v` value must parse and be non-zero for `r`; the string
value must equal the numeric mirror). To reproduce the old failure on a good file, rewrite one
resistor template to `#2` and T23 fails immediately.

#### An instrument is bound by a SHEET-scoped key (W22)

A meter can draw correctly, be wired correctly, simulate without a single warning - and still
read **0 V**, because it is not bound to the sheet. Multisim matches an instrument's property
block to the placed part through one string:

```xml
<!-- CIITHierDoc/InstrumentsData -->
<CSourceSymbolCollectNode Class="CSourceSymbolCollectNode"
                          CompLongName="&ASCXMM1#1/out:" />
                                          ^refdes  ^n  ^DesignSheet/@Title
```

The suffix after `/` is the **document's sheet title**, not a constant. A generator that
builds on a template project inherits *that* project's title (e.g. `Skeleton`) while
its instrument code writes a fixed suffix (`Project:`), so the key never matches and the
meter keeps no measurement mode and no probe node:

```
simulation runs, no errors, every meter shows 0 V     <- the whole symptom
```

The reference project shows the correct shape - title and key agree, and the stored display
value proves a real reading was latched:

```
reference.ms14     DesignSheet@Title=reference    key=XMM1#1/reference:
                  NI_EWB_CURRENTDISPLAYDATA_VALUE = "4.611 V"   (and "86.067 mV" on the other)
```

##### The rule

Rename the document identity **once, textually, over the finished XML**, to the output file
stem - that is what a GUI-saved project looks like, and it is the only way the keys and the
sheet can agree:

```python
xml = self.xml()                                    # build first
stem = os.path.splitext(os.path.basename(path))[0]
if stem != self.sheet_name:
    xml = xml.replace(self.sheet_name, stem)        # all six copies at once
self.sheet_name = stem
ms14.pack(xml, path)
```

The keys themselves only need re-deriving from that name:

```python
# at construction: the sheet's identity, decoded
title = next(self.root.iter("DesignSheet")).get("Title")
self.sheet_name = title[len("&ASC"):] if title.startswith("&ASC") else title

# at save: rebuild only the keys, from that name
def set_sheet_name(self):
    for node in self.inst_data:
        base = (node.get("CompLongName") or "").replace("&ASC", "").split("#", 1)[0]
        node.set("CompLongName", "&ASC" + base + "#1/" + self.sheet_name + ":")
```

⚠️ Two failure modes bracket this, and both look unrelated to instruments:

| what you do | what happens |
|-------------|--------------|
| rename only `DesignSheet/@Title` to the file name | documents disagree with themselves -> **crashes on open** |
| leave the skeleton's name everywhere | title/file/keys never agree -> **opens, simulates, every meter reads exactly 0 V** |

The `RefDesInfoData/@RefDes` strings carry an absolute path *and* the sheet name, so a textual
rename of the whole XML fixes those too (the path then points at the file you just wrote,
which is what the GUI stores).

| Rule | Why |
|------|-----|
| W22a | the key suffix **must equal** `DesignSheet/@Title` | otherwise the block is orphaned: no mode, no probe, `0 V` |
| W22b | the sheet name **must equal the output file stem**, and if you rename it you must rename **every** copy at once | it appears in six places - `Project/@Name`, `Sheet/@SheetName`, `DesignSheet/@Title`, `RefDesInfoContainer/@CIR`, every `RefDesInfoData/@RefDes` path, and the instrument keys. Rename one and **Multisim crashes on open**; rename none and the keys cannot match the sheet the application derives from the file name, so **every meter reads 0 V** |
| W22c | the title is string-encoded (`&ASCreference`) but the key is plain (`reference`) | strip the `&ASC`/`&UNI` prefix; a key of `&ASCSkeleton` binds nothing |
| W22d | keep the *other* instrument keys coherent (`NI_EWB_MEASUREMENT_MODE` 1 = volts, `NI_EWB_SIGNAL_MODE`, `NI_EWB_SIMULATION_ALLOW` 1) | the mode alone does not bind the meter |
| W22e | **scrub the template project's name at save time** (`xml.replace(old, stem)`) and keep the template's own identity neutral | an inherited name either kills the binding (`0 V`) or, if renamed in one place only, crashes the application (W22e below) |
| W23 | **an instrument's model is named `X<refdes>_<doc number>`** and its card is the two-terminal `I_multi_meter`/`R_multi_meter` subckt | a synthesised name (`XMM1_V`) netlists as an ordinary subcircuit: the run is clean and the dial stays at `0` |
| W24 | **connection objects carry page coordinates, but coordinates do not join (superseded by W33)** | positions are for drawing; joins need a shared id - see W33 | and a floating instrument reads `0` without any warning |
| W26 | **build on a project that already measures**, and rebuild its document layer for your own circuit (registry, pins with `lastnet`, per-refdes records, net labels); one instrument, one model | an inherited document layer leaves the parts unregistered, so the sheet simulates and every instrument reads `0` |
| W27 | **a refdes is `[A-Za-z]+[0-9]+`** - a trailing letter+digit means "section N of part X" and collapses parts into one element (`Duplicate component name found 'qq1'`, warning only) | the netlist still validates and the sheet runs, but the absorbed parts lose their connections and a whole stage disappears |
| W29 | **database model cards are untrusted**: gate emission coefficients (`NF`/`NR` within ~10% of 1.0) and re-store any kept/copied card through `set_model_text()` so `_flatten_card()` strips lone `+` tokens | `NF=1.5`-style cards collapse the DC operating point; a flattened multi-line card fails the netlist check (`Invalid parameter name '+'`) and the simulation never starts |
| W31 | **a high-Z node held up only through a diode + emitter follower gets a bleeder (10k to ground)** - without a DC path Newton fails from the seeded start (verified offline: 3 of 4 input states) | one resistor gives the solver a DC path; truth table unchanged |
| W32 | **the offline oracle must be validated before use** - `dcsolve` once built zero transistor models (type parsed as `NPN(`, femto suffix `f` unparsed) and reported `ok` on circuits with no BJTs | check the model count equals the BJT count and reproduce one GUI reading (Q1_RTL_OR3: V(6)=4.610 V vs GUI 4.611 V) before trusting any number |
| W33 | **the editor joins objects by id, never by position**: two wires meet only when they reference one shared object (two wires at a corner: one object; three or more: a junction) | a file with correct net membership shows islands in Multisim: meters near 0 V with fV noise, supply and ground disconnected |
| W34 | **Multisim's COM server (32-bit PowerShell) gives its own netlist** (`ReportNetlist(0,0,path)`) and the editor's connectivity without the GUI | the final judge for connectivity; close the sheet in Multisim first |

#### Template leakage: the skeleton's name must not survive (W22e)

A generator that starts from a template project inherits that project's **identity**, and the
identity is not just a title - it is the string the whole document is scoped by. Two opposite
failures come from mishandling it, and both look like instrument problems:

| action | symptom |
|--------|---------|
| keep the template's name (e.g. `Skeleton`/`TestOnlyInventor`) | opens, simulates, **every meter reads 0 V** - keys say `/<template>:` while the application scopes by the *file* name |
| rename only `DesignSheet/@Title` | **crashes on open** - the other five copies still hold the old name |

So treat the template name as contamination and scrub it in one place - over the finished
XML, where you know the output stem:

```python
xml = self.xml()
stem = os.path.splitext(os.path.basename(path))[0]
for old_name in {self.sheet_name, "Skeleton", "TestOnlyInventor"}:   # current + legacy
    if old_name and old_name != stem:
        xml = xml.replace(old_name, stem)          # every copy at once, paths included
self.sheet_name = stem
ms14.pack(xml, path)
```

Rules:

- **Keep the template's identity neutral** (`tools/xml/skeleton.xml`, project `Skeleton`) so a
  leak is recognizable instead of plausible. Do not name the template after a real project.
- **Scrub at save, not at construction** - the output stem is only known then.
- **List the legacy names explicitly.** A skeleton that was renamed once still feeds its old
  name to anyone who has an old copy; the scrub is cheap and idempotent.
- **A textual replace is correct here** precisely because the name is a *path component* too:
  `RefDesInfoData/@RefDes` embeds `<folder>\<sheet>.ms14` and must point at the file you just
  wrote, which is exactly what the GUI stores.
- **Verify with a count**, not by eye: `ms14.unpack(out).count(old_name)` must be `0`, and
  every identity field (`Project/@Name`, `DesignSheet/@Title`, `RefDesInfoContainer/@CIR`,
  instrument keys) must equal the stem. T24 enforces both for generated files.

Guard: **T24** - every `CSourceSymbolCollectNode` must parse as `<refdes>#<n>/<sheet>:`, its
sheet must be the document's `DesignSheet/@Title`, and its refdes must be a placed part. It is
silent on `reference.ms14`; rename that file's title and it fails immediately.

A 0 V meter has now been seen from three different causes, so check them in this order:
**binding (W22)** -> mode/card (`R_multi_meter`, T21) -> polarity/pins (`checkmeterroles.py`).
The stored display string (`NI_EWB_CURRENTDISPLAYDATA_VALUE`) only updates on Run, so read the
binding first; it is the only one that silently yields exactly `0 V` with a healthy netlist.

#### An instrument's model name is part of the protocol (W23)

A meter can be correctly placed, bound, wired and simulated - and its dial still sits at
`0` - because its **model name does not look like an instrument model**. Two GUI-saved
projects agree on the shape:

```
donor (Electronics1.xml)   .subckt XXMM1_131568832    .subckt XXMM3_131568832
GUI-saved (reference)      .subckt XXMM1_278580792    .subckt XXMM2_278580792
generated (before)         .subckt XMM1_V             <-- synthesised, wrong shape
```

`X` + **refdes** + `_` + a **document-scoped number**. Generate `"<refdes>_<tag>"` instead and
the netlister emits a plain subcircuit call: the schematic runs, no error is raised, and the
dial has nothing to display - `0` on every range.

```python
# ms14build.add_instrument
self._borrow_model(part, palette, mdl, "V" if mode == 1 else "A",
                   name="X" + refdes + "_" + self.circuit_id)   # XMM1 -> XXMM1_212316656
```

Two related conventions in the same block:

| Item | Rule |
|------|------|
| model name | `X<refdes>_<doc number>` - never arbitrary, never shared between instruments |
| card body | `.subckt <same name> 2 1  I_multi_meter 1 2 DC 0  R_multi_meter 2 1 1e9 .ends` (the `R_multi_meter` value *is* the mode: 1e9 = voltmeter, ~1e-5 = ammeter, T21) |
| stored reading | `NI_EWB_CURRENTDISPLAYDATA_VALUE` holds a formatted value **with its unit** (`"4.611 V"`, `"86.067 mV"`); write `"0 V"`, not `"0"` |

Verify from the netlist, not the drawing: `python netlist.py <out>.ms14` must end with
`XMM1 Y 0 XXMM1_<n>` - an element whose model name starts with `X` before the refdes.

#### Connection objects carry positions, but positions do not join (W24, superseded by W33)

Old claim (wrong): equal coordinates join pins. They do not. Keep writing page coordinates (`symbol offset + connector centre`) because genuine sheets carry them and geometry checks use them, but a 0 V / island bug is fixed by sharing one corner object (W33), not by moving coordinates. Guard T25 stays as a drawing check, not a connectivity proof.

#### The control defines truth: a GUI file may "fail" your own tests (W25)

When a GUI-saved project is the control, run the suite on **it** and read the failures as a
statement about the *tests*, not the file. `reference.ms14` simulates perfectly and still trips:

| test | what it reports on the working file | why the test is wrong |
|------|-------------------------------------|-----------------------|
| T11 | 5 ports are in no net | the GUI leaves unused pin objects on symbols it has edited |
| T16/T17 | the all-purpose `v... ac #3 #5 + distof1 ...` template | that template is legal in the application; the single-line policy only applies to generated cards |
| C10 | the resistor MODPEX card starts with `*` | unused/unreferenced card, never netlisted |
| `checkmeterroles` | `XMM1 + -> 6` | the working sheet uses numbered nets, not our names |

Consequence: keep the strict checks gated on **generated** files (`--ref` makes the flag
strict for those only), and use the control to *find* invariants, never to fail it (R7/R8).

Corollary for delivery: if a generated sheet still diverges from a working reference on a
subsystem you cannot otherwise verify, ship the reference sheet with its identity renamed -
`xml.replace(old_name, new_stem)` over the whole document - and record the remaining gap
honestly (here: the per-instance registry, `RefDesGUIDsForSave` / `RefDesInfo` /
`ComponentPins`, which the generator still stubs with 1 entry instead of one per part).


#### A refdes is LETTERS + DIGITS, nothing else (W27)

`Q1A1` does not name a transistor called "Q1A1". The application reads it as **section `A1` of
the multi-section part `Q1`**, so every part sharing that base collapses onto one element:

```
Warning: RefDes 'q1', element 'qq1_1':  Duplicate component name found 'qq1'
Warning: RefDes 'q1', element 'qq1_2':  Duplicate component name found 'qq1'
```

The netlist check still reports `0 error(s)` - only warnings - and the sheet opens and runs, so
nothing looks broken until you read a meter. The survivors keep the element name and the others
lose their connectivity, which is exactly how a stage silently disappears.

Rule: a refdes is `[A-Za-z]+[0-9]+` - one letter run, then digits. Multisim appends a digit
silently to a refdes that has none: `Rbleed` came back as `Rbleed1` in the netlist report.

| good | bad | why |
|------|-----|-----|
| `Q11`, `Q12`, `R23`, `D1`, `TN11`, `V1` | `Q1A1`, `Q1B1` | trailing letter+digit = multi-section suffix |
| `Q1`, `Q2` | `Q1A` | a bare trailing letter is a section id too |
| `0` (the ground part) | `VCC` as a *part* name | reserve net/power names for nets; a source part is `V1` |

Check it mechanically, it costs one regex:

```python
bad = [r for r in refdes if not re.match(r"^[A-Za-z]+[0-9]+$", r) and r != "0"]
```

Generate per-stage numbering instead of string-concatenating a tag onto a name
(`"Q1A" + "1"` -> `Q11`, `"Q4" + "2"` -> `Q25`), and keep net names out of the part namespace.

#### What was verified on Q2 (2026-10-27)

Root cause: two wires meeting at a corner used two different connection ids, so Multisim split the net (W33). V1, the VCC rail and the ground return floated; every node read ~0 V.

- `wiregraph.py`: Q2 CONNECTED (16 islands / 16 nets, was 36). Q1Manual, Q1_RTL_OR3 CONNECTED.
- `multisim_netlist.py`: MATCH with the intended 16 nets.
- ngspice (`spice_check.py`): AND truth table. Low inputs X 3.66 V / Y 24 mV; high inputs X 34 mV / Y 4.31 V.
- dcsolve oracle (`truthtable.py`): same shape (X 3.756 / 0.019 V, Y 0.001 / 4.655 V).
- Q3 sheets in the project root still fail `wiregraph.py` the same way; fixed copies were verified in `_bak/` only.

#### Connectivity is by object reference, not by position (W33)

The editor joins pins through the wire objects: a wire lists its two end objects (`Connect1`,
`Connect2`); a pin connector and a junction list the objects they connect (`ConnectList`).
Two objects at the same coordinates are NOT joined. A file can list the right nets (CiNode
membership) and still show the editor islands.

Rule: where exactly two wires meet, both wires must reference ONE shared connection object.
Where three or more meet, use a junction object whose `ConnectList` names each stub. Two
different ids at one point leave both wires dangling. The builder broke this in three places
(the far corner of a trunk, a bus group with one pin and one neighbour, and the two-pin star).
Fixed in `ms14build.py`; Q2 went from 36 wire islands to 16.

Fingerprint: meters read about zero, even negative femto-volt noise, in every input state, while
`checknets`, `checkjoins`, `preview` and `netlist.py` all pass. In Multisim's netlist report the
supply's pins sit alone and the pull-down returns sit on a second ground net.

Checks, in order: `python wiregraph.py <out>.ms14` must print CONNECTED; then
`python multisim_netlist.py <out>.ms14` must print MATCH (W34). Position-based checks cannot see
this class of bug.

#### Multisim's COM API gives its own netlist, without the GUI (W34)

`MultisimInterface.MultisimApp` is a 32-bit COM server: call it from
`C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe`. From the 64-bit shell it reports
"class not registered". Late-bound calls work through `[Type]::GetTypeFromProgID` and
`InvokeMember`; a direct `New-Object -ComObject` property read crashed PowerShell.

Verified:
- `Connect()`, `OpenFile(path)` (returns the circuit), `IsConnected`, `LastErrorMessage`,
  `VersionInfo` ("Multisim 14.2").
- `ReportNetlist(0, 0, outPath)` writes the netlist report: net, sheet, component, pin. It takes
  exactly three arguments.
- `EnumInputs` lists the sources (V1, V2, V3); `EnumComponents` lists the parts (instruments are
  not listed).

Not working: `DoDCOperatingPoint`, `SetOutputRequest` and `GetOutputData` take a string array of
output names we could not find ("Output not found"). Use ngspice (`spice_check.py`) or the oracle
for voltages until that is solved.

Caveat: `OpenFile` of a path that is already open in Multisim reuses the open document, with its
old content. Close the sheet in Multisim, or stop the instance the tool started, before a check.

#### The database's model card is untrusted data (W29)

Two independent ways a database-sourced card kills the simulation, both silent:

1. **Bad parameter values.** This install's 2N3904 row carries emission coefficients far from
   1.0 (`NF=1.5 NR=2.9 NE=3.3`). Verified offline with those cards on Q2: X = 8.3 V on a 5 V
   supply and Y = -0.35 V, physically impossible. Gate every card: `NF`/`NR` must be within
   ~10% of 1.0, else keep the donor part's proven card.
2. **Lost newlines.** A multi-line card stored with its `+` continuation markers but without
   newlines makes the SPICE parser read `+` as a parameter name:
   `Error: Element '2n3904 bjt_npn_l': Invalid parameter name '+'` in the netlist check, 2
   errors, and the simulation never starts. Any card that is kept or copied must be re-stored
   through `set_model_text()`, whose `_flatten_card()` joins continuations and strips lone
   `+` tokens. Cloned palette templates are NOT safe as-is. Same bug hit the synthesized
   MOSFET cards (`NMOS_MODEL`/`PMOS_MODEL` carried a `+` token; `_patch_model` wrote it raw) -
   fixed by single-line constants plus `_flatten_card` in `_patch_model`/`_set_model`.

Rule: never write a card into a file that did not just pass through `set_model_text()`, and
never trust a card whose emission coefficients you have not read.

#### A high-Z node held up through a diode needs a bleeder (W31)

In a cascaded totem-pole chain, the node between stages (here X) is pulled up only through
`Q14 -> D1` from a stage that switches itself off. With no DC path to ground, Newton does not
converge from the seeded start at 3 of 4 input states (verified offline with 1T in place of
the bleeder). A 10k resistor from the node to ground gives it a DC path, loads the emitter
follower by 0.37 mA, and leaves the truth table unchanged (X = 3.756 V / 0.019 V, Y = 0.001 V /
4.655 V). How Multisim itself behaves at that state is not verified offline.

Generalize: any node whose only DC paths are (a) through a diode-connected transistor fed by
an emitter follower that can turn off, and (b) into reverse-connected bases, gets a bleeder.

#### Diagnosing an instrument that reads 0 (playbook)

Ordered by what each check rules out, cheapest first:

1. **Wire joins first.** `python wiregraph.py <file>` must print CONNECTED. SPLIT/ALONE names the exact pins. Position coincidence proves nothing (W33).
2. **Multisim's own netlist.** `python multisim_netlist.py <file>` must print MATCH (W34, 32-bit PowerShell, COM). This is the editor's answer.
3. **Independent voltages.** `python spice_check.py <file> --in <vsrc..> --out <nets..>` (ngspice) and `python truthtable.py` (oracle, W32) must agree with the intent before any GUI run.
4. **Then binding and cards.** Instrument keys/mode/subckt (W22/W23, `checkmeterroles.py`), database cards (W29), DC path (W31).
5. **Live panels last.** Read open meter panels; file latches alone prove nothing.

Do not debug in this order: topology before connectivity, model cards before joins.

#### Build on a sheet that already measures (W26)

Every other rule can be satisfied and an instrument still reports `0`, because a project file is
not just a schematic: it is a schematic **plus a document layer** the application maintains
around it. Generating over a bare template means inheriting the template's document layer, and
that layer is what an instrument is resolved through.

So do not fight it - **start from a project the application itself has opened, simulated and
measured on**, and rebuild only what describes your own circuit:

```python
# make_circuits.builder
pal  = B.Palette("xml/<donor>.xml")                     # glyphs for the parts
skel = ms14.unpack("xml/reference_sheet.ms14")           # a sheet that measures
b = B.Builder(skel, pal); b.clear()
b.inst_palette = B.Palette("xml/reference_sheet.xml")    # instruments come from it too
```

Five things follow from that, and each one was a separate silent `0`:

| layer | rule | symptom when it is the template's |
|-------|------|-----------------------------------|
| instrument binding | meter part, symbol, model card and the whole `InstrumentProperties` block are **cloned from the reference sheet** | dial shows `0` on every range |
| per-part registry | `RefDesGUIDsForSave` carries **one entry per placed part** (`CiCompGUID` = the component's `InstanceID`, `InstanceGUID` = fresh) | nothing resolves the part's instance |
| pin registry | `ComponentPins` carries **one `CSCH_CAPVirtualComponentPin` per pin**, with `lastnet` = that pin's net | an instrument cannot resolve the node it probes |
| per-refdes records | `RefDesInfoContainers/CIRToInfoMap/CIRToInfoMapItem` carries **one entry per refdes** (`CIRKey`, `RefDesInfo/RefDesInfoData@RefDes`, `Prefix`, `Number`) | the part has no per-instance SPICE record |
| net labels | `CDesignNetContainer/NetLabels` holds **one `CSchDesignNetLabel` per net**, `LastNetName` = the net | net names stay unresolved; a name-based probe finds nothing |

Rebuild them from the finished sheet, never by hand, and never leave the template's leftovers in
place (a stale record either names a part that no longer exists or renames one of your nets):

```python
def save(self, path):
    xml = self.xml()
    ...
    self._rebuild_ref_classes()        # index by real class            (W20)
    self._rebuild_instance_registry()  # parts, pins with lastnet, per-refdes records
    self._rebuild_net_labels()         # one record per net            (W26)
    self._sync_circuit_refs()
```

One instrument, one model: a GUI-saved project never shares a meter model between two meters.
Force a distinct model per instrument, named `X<refdes>_<doc number>` (W23), even when both
instruments are cloned from the same reference part - cloning shares the *source* model id,
which silently collapses them into one.

Check the counts, they are a fingerprint:

```
components == RefDesGUIDsForSave == per-refdes records
pins       == ComponentPins entries
nets       == CSchDesignNetLabel entries
instruments == CSourceSymbolCollectNode entries, each a distinct model
```

#### The component's *database row* must not re-declare the model

A part carries **two** records, and they are not the same thing:

| where | what it is | name it must use |
|---|---|---|
| `CiModel/Attributes[1]/CiaCString` | the model the element line calls via `%m` | the CiModel's own name, `<refdes>__<part>__1` |
| `CiComponent/Attributes[4]/CiaCollString` strings[5] | a snapshot of the **database row** the part was placed from | the database's own name, `Q2N3904/ON` |

A generator that clones a palette part keeps the donor's database row: `strings[1]` still
says `2N2222A`, `strings[3]` says `Q2N2222A`, `strings[5]` still carries the donor's card.
The donor is self-consistent that way - its row says `Q2N2222A` while its CiModel says
`2N2222A__BJT_NPN__1`, which is exactly the point. Writing the *renamed* card into the row
instead produces a file that declares one model name **twice**:

```
======= SPICE Netlist check completed, 0 error(s), 0 warning(s) =======
Warning: Singular matrix. Check node 14. Ensure it is not floating with respect to net 0
Simulation canceled
```

Multisim builds a model per definition it finds, and the copy that no element references
keeps its internal device nodes - the solver meets a node with nothing on it. Watch the
node number move when you change a card (19 -> 14): that is the tell that it is a *device
internal* node, not a schematic net.

Rules:

- **Populate the row from the database**, not from the CiModel: `strings[1]` <- part name,
  `strings[3]` <- model name, `strings[5]` <- flattened database card
  (`ms14build.Builder.set_db_record`).
- **Several parts may share one row name** - twelve 2N3904s carry twelve identical rows in a
  real schematic. Only a row that shadows a *CiModel* name is a defect.

`checksim.py` **C11** fails when a component's database row declares a name a CiModel
already defines. It stays quiet on a shared row name, and on the donor.

#### Two more ways the *expanded line* goes wrong

**A slot that exists but holds the wrong value.** `#n` is positional, not semantic. The
stock resistor template reads its value from `#1`, while the value actually lives in
`parameters[1]` (slot `#2`) — so the line came out with the missing-value placeholder in
front of the model name:

```
r<refdes> <n1> <n2> 0 vres<refdes> ... .model vres<refdes> r(...)
      ^slot #1=0                              ^extra token
Warning: element 'rra': Too many arguments for function 'r'
Error:   element 'rra': Unsupported mathematical function 'r'
SPICE instantiation of component 'rra' failed. Component will be ignored by simulation.
```

A resistor needs one clause, so write it that way (`set_spice_template(part,
"r%p %t1 %t2 #2")` -> `r<refdes> <n1> <n2> <value>`), and check the *shape* of the line.

**A node count that does not match the device.** A MOSFET element is
`m<ref> <drain> <gate> <source> <bulk> <model>` — five nodes. Writing
`m%p %tD %tG %tS %m` produces four tokens after the name and the model is silently eaten as
the bulk node. The database template ties bulk to source (`m%p %tD %tG %tS %tS %m`), so copy
that instead of inventing a shorter one.

Expected line shapes (the quickest sanity check available without a simulator):

| element | tokens | example |
|---------|--------|---------|
| `r` | 4 | `r<refdes> <n1> <n2> <value>` |
| `v` | 4-8 | `v<refdes> <n+> 0 dc <value>` |
| `q` | 5-6 | `q<refdes> <c> <b> <e> <model>` |
| `m` | 6-7 | `m<refdes> <d> <g> <s> <b> <model>` (bulk tied to source) |
| `x` | >= 3 | `x<refdes> <pins...> <subckt>` |

Rules for any generator:

1. **Never copy a vendor template verbatim into a single-line field.** Keep only the
   clauses you need; every removed clause also removes its `#n` references.
2. **Write the parameters you reference** — `set_spice_template` resizes `parameters`,
   `doubles` and `paramindicators` together, so the slot count and the template agree.
3. **Add two static checks.** T16: fail if a template contains ` + `, or if any `#n`
   exceeds the parameter count. T17: expand the template and assert the token count for
   its element letter (table above). Both are cheap, both catch the whole family of
   "simulation refuses to start" errors before the model ever runs.
4. **Domain expectation** for a DC source: `v<ref> <n+> <n-> dc <value>` and nothing else.
   Deviations are a bug, not a feature.

### Part shapes by family (what to expect when you look one up)

The database holds tens of thousands of parts; these are the *shapes* worth recognising, not
specific devices. Query any name and compare against this table:

| Family | Pins | Pin family | Instance template | Card |
|--------|------|-----------|-------------------|------|
| BJT (NPN/PNP) | 3 | `$ANALOG$` | `q%p %tC %tB %tE %m` | Gummel-Poon `.MODEL ... npn/pnp` |
| diode | 2 | `DIODE` | `d%p %tA %tK %m` | `.MODEL ... d(...)` |
| MOSFET, discrete | 3 | `MOS_3TEN` | `x%p %tD %tG %tS %m` | `.SUBCKT` (hence the `x` element) |
| MOSFET, configurable | 3 | `$ANALOG$` | `m%p %tD %tG %tS %tS %m %S0` | bare `.model NMOS/PMOS` - parameters live in the instance |
| resistor | 2 | `$ANALOG$` | `r%p %t1 %t2 #1` (value at `parameters[1]`) | value-driven |
| DC source | 2 | `$ANALOG$` | `v%p %t1 %t2 dc #1` (value at `parameters[1]`) | `VDCP` |
| ground | 1 | `POWER_SOURCES` | *(none - not a netlist element)* | `EMPTY` |

Families worth knowing: `BJT_NPN`, `BJT_PNP`, `DIODE`, `SCHOTTKY_DIODE`, `SWITCHING_DIODE`,
`MOS_ENH_N`, `MOS_ENH_P`, `RESISTOR`, `POWER_SOURCES`.

WARNING: **pin order is per part, not per family.** Two transistors of the same family can
list their pins in different orders, so the DB `pinout` of *that* part is the only safe
source. Never assume, and never reuse a template written for another part without checking
every `%t<pin>` label against the pin names you actually have.

### Symbols: the one thing the DB will not give you

`SYS_SYMBOL_PICTURE.Image` is a **custom-compressed** drawing blob (841 B -> 3,877 B for the
diode). Measured entropy 7.77 bits/byte; not zlib / raw-deflate / gzip / bz2 / lzma, and not
PKWARE DCL despite the leading `0xAA`. Do not burn time on it.

Consequence — **check this before trusting donors**:

- All 133 sample `.ms14` files under `samples/` store components with **no inline symbol**
  (`SymCompID` never resolves inside their `Objects` collections): 0/133 usable as symbol
  donors. An earlier `multisim_parts.py` index had exactly this limit: names and model
  strings only - which is why the database replaced it.
- Real projects (`<PROJECT>/Multisim_old_project/*.ms14`, `<SKILL_DIR>/tools/xml/*.xml`, and the user's own
  `~/Documents/National Instruments/**`) **do** carry glyphs, but only for
  `RESISTOR_VIRTUAL`, `DC_POWER`, `GROUND`, one NPN glyph donor and 74-series ICs.

So the working split is:

1. **Electrical truth -> database** (`multisim_db.py`): name, pinout order, pin family,
   template, model card.
2. **Glyph -> synthesized** (`mosfet.py` style: clone an existing transistor symbol, redraw with
   `CODLineComp`/`CODEllipseComp` primitives, rename pins) or cloned from a project donor.
3. Write the DB model card + template into the part so Multisim simulates the real device.

### Wiring a DB part into a generated circuit

```python
import multisim_db as D, ms14build as B

p = D.part("<part>")                       # real model + pin order
pal = B.Palette("<SKILL_DIR>/tools/xml/<donor>.xml")      # glyph donor project
b = B.Builder(open("<SKILL_DIR>/tools/xml/<skeleton>.xml").read(), pal); b.clear()

q = b.add_part(pal, pal.pick("<bjt-donor>"), 400, 300, "Q1")   # glyph donor
q.set_model_text(p["spice"])               # the real model card from the database
b.connect_net("C", [(q, "C")])             # pin names come from the DB order
```

Rule of thumb: **if it is a number, pin name or model parameter, read the database.
If it is a shape, synthesize or clone it.**

### Applying a database model to a placed part

The generator does this in one call — `make_circuits.py` wraps it as `db_part()`:

```python
import multisim_db as D

q = b.add_part(pal, Q, 430, 330, "Q1")        # glyph cloned from the transistor donor
q.set_model_text(D.part("<part>")["spice"], "<part>")
```

`set_model_text()` rewrites `CiModel/Attributes[1]/CiaCString@String` (the `&ASC`-prefixed
card) and the model `LocalName` (`&ASC<refdes>__<part>__1`). Verified: after this call each
transistor carries the real database card instead of the donor's.

### What the database does *not* give the generator

⚠️ Configurable parts have **empty model cards** — the parameters live on the instance:

```
<configurable-N>   template: m%p %tD %tG %tS %tS %m %S0     spice: .model NMOS nmos
<configurable-P>   template: m%p %tD %tG %tS %tS %m %S0     spice: .model PMOS pmos
```

For a `.ms14` you must supply the parameters yourself, so `mosfet.py` writes explicit
LEVEL-1 cards (`VT0`, `KP`, `GAMMA`, `TOX`…) that name the device unambiguously. Same for
`RESISTOR`/`DC_POWER`: the card is `r/v` line metadata, the value is what you set.

Discrete devices *are* complete and worth taking verbatim - any part whose card is a plain
`.MODEL`/`.SUBCKT` with real parameters. Subcircuit-based ones use the `x%p ...` element form.

```ponytail
# ponytail: the totem-pole level-shift diode is drawn as a diode-connected transistor
# (base tied to collector), not a two-pin diode glyph. Electrically V_BE ~= 0.7 V matches
# the diode's V_F closely enough, and the model card is the same device.
# ceiling: no two-pin diode glyph exists in any project available locally.
# upgrade: synthesize one like mosfet.py does (polyline triangle + bar), then attach the
#          diode's card with set_model_text().
```

### Database maintenance

```bash
# after a Multisim upgrade, or to pick up new user parts
cd <SKILL_DIR>/tools/dbms && python jet2tsv.py                    # re-dump master (~59 s)
python jet2tsv.py "<MS_USER>/database/UsrComp_*.usr" dump_user    # separate dump dir
set MSDB_DUMP=<SKILL_DIR>/tools/dbms/dump_user                    # point dbq.exe at it
python <SKILL_DIR>/tools/multisim_db.py where                     # confirm what was found
```

### Alternative: Multisim scripting API

Multisim 14.x includes COM automation (see `<MS_HOME>/Multisim.chm`, chapter "Automating Multisim"):

```python
import win32com.client

ms = win32com.client.Dispatch("Multisim.Application")
ms.Visible = True
doc = ms.ActiveDocument
circuit = doc.Circuit

# Place component via COM (requires running Multisim GUI)
db_path = ms_paths()["data"] + "/"        # database folder, any version
comp = circuit.PlaceComponent("RESISTOR", "1k", 100, 100)  # x, y in mils
```

**Tradeoff**: COM requires Multisim running, slower than direct `.ms14` generation, but accesses full database without parsing Jet format.

**Recommendation**: Use samples for scripted generation, COM only for interactive/debugging workflows.


## Practical workflow

### Step 1: look the part up in the database

There is no sample-file index any more (`multisim_parts.py` was removed: it only ever
listed *names*, and none of the samples carry symbols). Query the database instead:

```bash
cd <SKILL_DIR>/tools
python multisim_db.py search <part> 5     # name / pins / family / function
python multisim_db.py show   <part>       # + pinout order, template, SPICE card
python multisim_db.py pins   <part>       # [<pins in DB order>]
```

### Step 2: place it

```python
import ms14build as B, mosfet, multisim_db as D

pal = mosfet.mos_palette("<SKILL_DIR>/tools/xml/<donor>.xml")   # glyphs + NMOS/PMOS
b = B.Builder(open("<SKILL_DIR>/tools/xml/<skeleton>.xml").read(), pal)
b.clear()

q = b.add_part(pal, pal.pick("<bjt-donor>"), 400, 300, "Q1")   # glyph donor
q.set_model_text(D.part("<part>")["spice"], "<part>")      # real device model
b.connect_net("C", [(q, "C")])
```

Glyphs come from the donor palette or `mosfet.py`; everything numerical comes from the
database. See "Wiring a DB part into a generated circuit" above.

### Step 3: verify before opening Multisim

```bash
python <SKILL_DIR>/tools/make_circuits.py
```

`make_circuits.py` prints one line per file and the net list is available from the same
builder instance, which is the fastest way to eyeball a topology:

```python
import pathlib, sys; sys.path.insert(0, "<SKILL_DIR>/tools")
import make_circuits as M
b = M.q1(pathlib.Path("<out>.ms14"))
for net, pins in sorted(b.netlist().items()):
    print("%-5s %s" % (net, ", ".join(pins)))
```

```
<input>   <source>.1, <R1>.1
<ref>     <source>.2, <R1>.1, ..., <refdes>.<pin>
<node>    <R1>.2, <R2>.2, <R3>.2, <Q1>.B
```

### Maintenance

| Task | Command |
|------|---------|
| build everything that is missing (fresh clone) | `python <SKILL_DIR>/tools/bootstrap.py` |
| verify the toolchain is ready without building | `python <SKILL_DIR>/tools/bootstrap.py --check` |
| rebuild the TSV dump (new Multisim version, new user parts) | `python <SKILL_DIR>/tools/dbms/jet2tsv.py` |
| rebuild the C++ query tool | `cmd //c <SKILL_DIR>\tools\dbms\build.bat` |
| check what was discovered | `python <SKILL_DIR>/tools/multisim_db.py where` |
| regenerate every circuit | `python <SKILL_DIR>/tools/make_circuits.py` |
| check a generated file's models | unpack it and read `CiModel/Attributes[1]/CiaCString@String` |

