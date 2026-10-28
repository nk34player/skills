# skills

A collection of agent skills, one folder per skill (see [Anthropic's skill format](https://github.com/anthropics/skills)).

| Skill | What it does |
|-------|--------------|
| [`multisim/`](multisim/) | Generate and manipulate NI Multisim `.ms14` circuit files: BJT/CMOS/transmission-gate logic, netlist + wire-level verification, ngspice cross-check |

## Using a skill

Copy the skill folder next to your project (or symlink it), then point your agent at its `SKILL.md`:

```bash
cp -r skills/multisim <PROJECT>/skills-multisim
```

Each skill is self-contained: `SKILL.md` + its `tools/` + `examples/`.
