#!/usr/bin/env python3
"""Multisim's own netlist for a sheet, through the COM API - no GUI, no focus.

    python multisim_netlist.py ../Q2_TTL_AND2.ms14

Asks the running Multisim 14 (it starts one hidden if needed) for ReportNetlist, then
compares every Multisim net with the sheet's logical net (CiNode). Prints MATCH, or each
logical net that the editor splits, joins to another net, or leaves with a floating pin.

Why: a file can pass every structural check and still be wired wrong in the editor - the
editor joins pins through wire ids, not positions (see wiregraph.py). This is the editor's
own answer. Needs the 32-bit Windows PowerShell (the Multisim COM server is 32-bit).
Instruments are not in the report and are ignored.
"""
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict

import wiregraph

PS32 = r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
HERE = os.path.dirname(os.path.abspath(__file__))

PS_SCRIPT = r"""
param([string]$File, [string]$Out)
$ErrorActionPreference = "Stop"
$t = [Type]::GetTypeFromProgID("MultisimInterface.MultisimApp")
$app = [Activator]::CreateInstance($t)
$f = [System.Reflection.BindingFlags]
$t.InvokeMember("Connect", $f::InvokeMethod, $null, $app, $null) | Out-Null
$circ = $t.InvokeMember("OpenFile", $f::InvokeMethod, $null, $app, @($File))
[System.__ComObject].InvokeMember("ReportNetlist", $f::InvokeMethod, $null, $circ, @(0, 0, $Out)) | Out-Null
Write-Output "REPORTED"
"""


def report(path):
    """Write Multisim's netlist report for `path`; return its text."""
    absf = os.path.abspath(path)
    out = os.path.join(tempfile.gettempdir(), "ms_netlist_%d.txt" % os.getpid())
    script = os.path.join(HERE, "_mnet_report.ps1")
    with open(script, "w", encoding="utf-8") as f:
        f.write(PS_SCRIPT)
    if os.path.exists(out):
        os.remove(out)
    p = subprocess.run([PS32, "-ExecutionPolicy", "Bypass", "-File", script, "-File", absf,
                        "-Out", out], capture_output=True, text=True, timeout=600)
    if not os.path.exists(out):
        raise SystemExit("Multisim did not write a netlist report:\n" + p.stdout + p.stderr)
    text = open(out, encoding="utf-8", errors="replace").read()
    os.remove(out)
    return text


def parse(text):
    """Multisim net id -> set of (component, pin)."""
    nets = defaultdict(set)
    for ln in text.splitlines():
        parts = ln.split()
        if len(parts) == 4 and re.match(r"^[A-Za-z0-9_]+$", parts[0]) and parts[0] != "Net":
            nets[parts[0]].add((parts[2], parts[3]))
    return nets


def wiregraph_logical(path):
    """logical net -> set of (component, pin) (Ground part named '0'), and member -> Multisim id."""
    _, logical, _, _ = wiregraph.analyse(path)
    logical_sets = {}
    for name, plist in logical.items():
        members = set()
        for p in plist:
            if p is None:
                continue
            comp, pin = p
            if comp == "0":
                comp = "Ground"
            if comp.startswith("XMM"):
                continue
            members.add((comp, pin))
        logical_sets[name] = members
    return logical_sets, {}


def main(argv):
    path = argv[0]
    text = report(path)
    ms_nets = parse(text)
    logical, _ = wiregraph_logical(path)
    ms_of = {m: nid for nid, members in ms_nets.items() for m in members}
    problems = []
    for name, members in logical.items():
        ids = {ms_of.get(m) for m in members}
        ids.discard(None)
        if members and len(ids) > 1:
            problems.append("SPLIT  logical net %-6s is %d nets in Multisim: %s"
                            % (name, len(ids), [sorted(ms_nets[i]) for i in ids]))
        for mid in ids:
            extra = ms_nets[mid] - members
            if extra:
                problems.append("SHORT  logical net %-6s joined in Multisim to %s" % (name, sorted(extra)))
        missing = [m for m in members if m not in ms_of]
        if missing:
            problems.append("FLOAT  logical net %-6s pins not in any Multisim net: %s" % (name, sorted(missing)))
    print("%s  Multisim nets=%d  logical nets=%d" % (os.path.basename(path), len(ms_nets), len(logical)))
    if not problems:
        print("  MATCH: Multisim's netlist equals the sheet's intended nets")
        return 0
    for p in problems:
        print("  " + p)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
