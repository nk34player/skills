#!/usr/bin/env python3
"""Bootstrap the Multisim toolchain on a fresh machine.

Nothing under tools/ that is *generated* is meant to be shipped: the C++ query tool
(dbq.exe) and the database dump (dump/*.tsv, ~120 MB) are build products. This script
creates whatever is missing and tells you exactly what it did.

    python bootstrap.py           # build what is missing
    python bootstrap.py --check    # report only, exit 1 if anything is missing

Steps (each skipped when already satisfied):
  1. dbq.exe        compiled from dbms/dbq.cpp   (MSVC vcvars32, or g++)
  2. dbms/dump/     Jet -> TSV dump, needs the Multisim database + access_parser
"""
import os
import pathlib
import shutil
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
DBQ = TOOLS / "dbms" / "dbq.exe"
DUMP = TOOLS / "dbms" / "dump" / "SYS_COMPONENT.tsv"


def have(tag, ok, hint):
    print("%-12s %-22s %s" % (tag, "ok" if ok else "MISSING", "" if ok else hint))
    return ok


def build_exe():
    script = TOOLS / "dbms" / "build.bat"
    print("building dbq.exe ...")
    r = subprocess.call(["cmd", "/c", str(script)], cwd=str(TOOLS / "dbms"))
    return r == 0 and DBQ.exists()


def build_dump():
    print("dumping the component database (about a minute) ...")
    r = subprocess.call([sys.executable, str(TOOLS / "dbms" / "jet2tsv.py")],
                        cwd=str(TOOLS / "dbms"))
    return r == 0 and DUMP.exists()


def main(argv):
    check = "--check" in argv
    print("Multisim toolchain in %s\n" % TOOLS)

    ok_exe = have("dbq.exe", DBQ.exists(), "run: python bootstrap.py")
    ok_dump = have("db dump", DUMP.exists(), "run: python bootstrap.py")
    have("preview.py", (TOOLS / "preview.py").exists(), "source file - should ship")
    have("test_files.py", (TOOLS / "test_files.py").exists(), "source file - should ship")

    if check or (ok_exe and ok_dump):
        return 0 if (ok_exe and ok_dump) else 1

    if not ok_exe and not build_exe():
        print("!! compile failed - install Visual Studio (vcvars32) or put g++ on PATH")
        return 1
    if not ok_dump and not build_dump():
        print("!! dump failed - is Multisim installed? (pip install access_parser)")
        return 1
    print("\nready.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
