"""Read/write NI Multisim .ms14 (and .ewprj) project containers.

Layout (confirmed against 18 real Multisim 14.1 projects, re-packed byte-identical):

    char     magic[36]   "MSMCompressedElectronicsWorkbenchXML"  (or "CompressedElectronicsWorkbenchXML")
    uint32   total        total uncompressed XML size
    uint32   pad          0
    repeat until total consumed:
        uint32 raw        uncompressed bytes in this block (max 900000)
        uint32 comp       compressed bytes in this block
        byte   data[comp] one PKWARE DCL implode block, ASCII mode, 4096 dict
"""

import struct

from pklib import explode, implode

MAGIC = b"MSMCompressedElectronicsWorkbenchXML"
MAGIC_EWPRJ = b"CompressedElectronicsWorkbenchXML"
MAX_BLOCK = 900000


def unpack(path):
    """Return the uncompressed XML text of a .ms14/.ewprj file."""
    blob = open(path, "rb").read()
    if blob.startswith(MAGIC):
        off = len(MAGIC)
    elif blob.startswith(MAGIC_EWPRJ):
        off = len(MAGIC_EWPRJ)
    else:
        raise ValueError("not a Multisim project: bad magic in %s" % path)

    total = struct.unpack("<I", blob[off:off + 4])[0]
    pos = off + 8
    out = bytearray()
    while len(out) < total:
        raw, comp = struct.unpack("<II", blob[pos:pos + 8])
        pos += 8
        out += explode(blob[pos:pos + comp])
        pos += comp
        if raw != len(out) - (len(out) - raw):  # keep raw for sanity below
            pass
    if len(out) != total:
        raise ValueError("size mismatch: header %d, decoded %d" % (total, len(out)))
    return out.decode("utf-8")


def pack(xml, path, magic=MAGIC):
    """Write XML text as a .ms14/.ewprj container."""
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    out = bytearray()
    pos = 0
    while pos < len(data):
        raw = data[pos:pos + MAX_BLOCK]
        comp = implode(raw, ctype=1, dsize=0x1000)
        out += struct.pack("<II", len(raw), len(comp)) + comp
        pos += len(raw)
    if not out:  # empty design still needs one block
        comp = implode(b"", ctype=1, dsize=0x1000)
        out += struct.pack("<II", 0, len(comp)) + comp
    head = magic + struct.pack("<II", len(data), 0)
    open(path, "wb").write(head + bytes(out))


if __name__ == "__main__":
    import glob
    import os
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "dump":
        os.makedirs("xml", exist_ok=True)
        for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "Multisim_old_project", "*.ms14"))):
            name = os.path.basename(f)
            xml = unpack(f)
            open(os.path.join("xml", name + ".xml"), "w", encoding="utf-8", newline="").write(xml)
            print("%-22s %8d bytes xml" % (name, len(xml)))
        sys.exit()

    # self-check: every real project must re-pack byte-identically
    checked = 0
    for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "Multisim_old_project", "*.ms14"))):
        original = open(f, "rb").read()
        xml = unpack(f)
        pack(xml, "roundtrip.tmp")
        rebuilt = open("roundtrip.tmp", "rb").read()
        assert rebuilt == original, "mismatch: " + f
        checked += 1
    os.remove("roundtrip.tmp")
    print("ms14 self-check ok: %d files re-packed byte-identical" % checked)
