#!/usr/bin/env python3
"""Multisim component database access - fast path over dbq.exe.

Layout:
  tools/dbms/dbq.exe           C++ query tool (compiled by tools/dbms/build.bat)
  tools/dbms/dump/*.tsv        one-time dump of the Jet database
  tools/dbms/jet2tsv.py        the dumper (Python, needs access_parser)

Databases (locations vary per machine - discovered, never hardcoded):
  master     <MS_DATA>/database/MSCOMP_*.PRD    ~240 MB, 57k parts
  corporate  <MS_DATA>/database/CPCOMP_*.PRJ
  user       <MS_USER>/database/UsrComp_*.usr    empty by default

  <MS_DATA> = %ProgramData%/National Instruments/Circuit Design Suite/<ver>/
  <MS_USER> = %APPDATA%/National Instruments/Circuit Design Suite/<ver>/

Usage:
    import multisim_db as D
    D.search("2N7000")            # [(name, {pins, family, function...})]
    p = D.part("2N3904")          # full record, incl. 'spice' (.MODEL card) and 'template'
    D.pins("2N3904")              # ['E', 'C', 'B']  (database pin order)
"""

import glob
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
DBQ = HERE / "dbms" / "dbq.exe"
DUMP = HERE / "dbms" / "dump"


def _glob1(*patterns):
    """Newest match over several path patterns, or None. Never hardcode drive/version/edition."""
    for pat in patterns:
        hits = sorted(glob.glob(os.path.expandvars(pat)))
        if hits:
            return hits[-1]
    return None


# Two layouts exist in the wild: version as a subfolder (ProgramData/AppData) and version
# inside the folder name (install folder, Public Documents).
_MS = (r"National Instruments\Circuit Design Suite\*\database",
       r"National Instruments\Circuit Design Suite*\database")

# Override any entry with MS_DB_MASTER / MS_DB_CORP / MS_DB_USER.
PATHS = {
    "master": (os.environ.get("MS_DB_MASTER")
               or _glob1(*[os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), p, "MSCOMP_*.PRD")
                           for p in _MS])),
    "corporate": (os.environ.get("MS_DB_CORP")
                  or _glob1(*[os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), p, "CPCOMP_*.PRJ")
                              for p in _MS])),
    "user": (os.environ.get("MS_DB_USER")
             or _glob1(*[os.path.join(os.environ.get("APPDATA", ""), p, "UsrComp_*.usr")
                         for p in _MS])),
}

_cache = {}


def _run(*args):
    exe = str(DBQ)
    if not DBQ.exists():
        raise FileNotFoundError("build it first: tools/dbms/build.bat  (%s)" % exe)
    env = dict(os.environ, MSDB_DUMP=str(DUMP))
    out = subprocess.run([exe] + [str(a) for a in args], capture_output=True, text=True, env=env)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "dbq failed")
    return out.stdout


def dbinfo():
    """Where the databases were found, and whether a dump is ready for dbq.exe."""
    return {"paths": PATHS,
            "dump": str(DUMP),
            "dump_ready": (DUMP / "SYS_COMPONENT.tsv").exists(),
            "dbq": str(DBQ)}


def part(name):
    """Full database record for one part, or KeyError."""
    if name in _cache:
        return _cache[name]
    try:
        rec = json.loads(_run("json", name))
    except RuntimeError as e:
        raise KeyError(str(e).strip()) from None
    rec["pinout"] = [p for p in rec["pinout"].replace("\r\n", "\n").split("\n") if p]
    rec["template"] = rec["template"].replace("\r\n", "\n").strip()
    rec["spice"] = rec["spice"].replace("\r\n", "\n")
    _cache[name] = rec
    return rec


def pins(name):
    """Pin names in database order (this is the order the SPICE template expects)."""
    return part(name)["pinout"]


def search(substr, limit=30):
    """Substring search over component names -> [(name, {pins, family, function})]."""
    rows = []
    for line in _run("search", substr, limit).splitlines():
        if not line.strip():
            continue
        name, rest = line.split(None, 1)
        meta = {}
        body = rest
        for tok in rest.split():
            if tok.startswith("pins="):
                meta["pins"] = tok[5:]
            elif tok.startswith("fam="):
                meta["family"] = tok[4:]
                body = rest.split(tok, 1)[1]
        meta["function"] = body.strip()
        rows.append((name, meta))
    return rows


def families():
    """{Family_ID: {'name': ..., 'group': ..., 'template': 'Q%d'|'U%d'|...}}"""
    out = {}
    for line in _run("fam").splitlines():
        f = line.split()
        if len(f) < 3:
            continue
        fid, name = f[0], f[1]
        tpl = f[-1] if "%" in f[-1] else ""
        grp = next((x[4:] for x in f if x.startswith("grp=")), "")
        out[fid] = {"name": name, "group": grp, "template": tpl}
    return out


def show(name):
    part(name)
    print(_run("show", name), end="")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "search":
        for n, m in search(args[0], int(args[1]) if len(args) > 1 else 30):
            print("%-28s pins=%-2s fam=%-4s %s" % (n, m.get("pins", ""), m.get("family", ""), m["function"][:60]))
    elif cmd == "show":
        for n in args:
            show(n)
    elif cmd == "json":
        print(json.dumps(part(args[0]), indent=2))
    elif cmd == "pins":
        print(pins(args[0]))
    elif cmd == "where":
        info = dbinfo()
        for k, v in info["paths"].items():
            print("%-10s %s" % (k, v))
        print("%-10s %s (dump_ready=%s)" % ("dump", info["dump"], info["dump_ready"]))
        print("%-10s %s" % ("dbq", info["dbq"]))
    elif cmd == "fam":
        for k, v in families().items():
            print("%-4s %-34s grp=%-3s %s" % (k, v["name"], v["group"], v["template"]))
    else:
        print(__doc__)
