#!/usr/bin/env python3
"""One-time dump of a Multisim Jet database to TSV (dbdump.cpp equivalent).

Why Python here: MSCOMP_S.PRD is Jet 3 (Access 97). The 32-bit Jet 4 ODBC driver and
ACE both refuse Jet 3 on Windows 11 ("Not a valid password", even for the empty
template), and relabelling the header version byte does not help. access_parser walks
the Jet pages directly, so it is the only local reader. Run this once; everything
downstream (dbq.exe, make_circuits.py) reads the TSV.

    python tools/dbms/jet2tsv.py [db] [outdir]

Cell escaping matches dbdump.cpp:  \\ -> \\\\   tab -> \\t   CR -> \\r   LF -> \\n
Binary columns are written as x<hex>.
"""

import os
import sys

TABLES = ["SYS_COMPONENT", "SYS_CONFIGURATION", "SYS_CONFIGURATION_GROUPS", "SYS_KIND",
          "SYS_MAPPING_COMP_MODEL", "SYS_MODEL", "SYS_MAPPING_COMP_SYMBOL", "SYS_INFO"]


def esc(v):
    if v is None:
        return ""
    if isinstance(v, (bytes, bytearray)):
        return "x" + bytes(v).hex()
    s = str(v)
    return (s.replace("\\", "\\\\").replace("\t", "\\t")
             .replace("\r", "\\r").replace("\n", "\\n"))


def dump(db_path, outdir):
    import contextlib, io
    from access_parser import AccessParser

    db = AccessParser(db_path)          # parser prints per-chunk warnings on stderr
    os.makedirs(outdir, exist_ok=True)
    for name in TABLES:
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                t = db.parse_table(name)
        except Exception as e:
            print("%-26s skip (%s)" % (name, type(e).__name__))
            continue
        if not t:
            print("%-26s empty" % name)
            continue
        cols = list(t)
        n = max(len(v) for v in t.values())
        with open(os.path.join(outdir, name + ".tsv"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\t".join(cols) + "\n")
            for i in range(n):
                f.write("\t".join(esc(t[c][i]) if i < len(t[c]) else "" for c in cols) + "\n")
        print("%-26s %8d rows" % (name, n))


if __name__ == "__main__":
    import glob

    def default_master():
        """Discover the master DB: version folders and edition letters both vary."""
        env = os.environ.get("MS_DB_MASTER")
        if env:
            return env
        pats = []
        for base in (os.environ.get("ProgramData", r"C:\ProgramData"),):
            for shape in ("Circuit Design Suite\\*\\database", "Circuit Design Suite*\\database"):
                pats.append(os.path.join(base, "National Instruments", shape, "MSCOMP_*.PRD"))
        for p in pats:
            hits = sorted(glob.glob(p))
            if hits:
                return hits[-1]
        raise SystemExit("master database not found; pass it explicitly or set MS_DB_MASTER")

    dump(sys.argv[1] if len(sys.argv) > 1 else default_master(),
         sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "dump"))
