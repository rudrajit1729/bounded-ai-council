#!/usr/bin/env python3
"""
Render the role prompts in ../prompts/*.md.

Each prompt file documents a role (purpose, inputs, instructions, output schema). The text a
model receives is the part between the markers

    <!-- BEGIN PROMPT -->
    ...
    <!-- END PROMPT -->

with every {{PLACEHOLDER}} replaced. Optional parts are wrapped in
<!-- IF NAME --> ... <!-- ENDIF NAME --> and kept only when NAME is true in the values passed.
Rendering fails if a placeholder is left unfilled, so a brief never reaches a model half-written.

Standard library only.
"""
from __future__ import annotations

import re
from pathlib import Path

from config import PROMPTS

BEGIN, END = "<!-- BEGIN PROMPT -->", "<!-- END PROMPT -->"
PH = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
COND = re.compile(r"<!-- IF ([A-Z0-9_]+) -->\n?(.*?)<!-- ENDIF \1 -->\n?", re.S)


def template(name: str) -> str:
    text = (PROMPTS / name).read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise SystemExit("prompt file %s has no BEGIN/END PROMPT markers" % name)
    return text.split(BEGIN, 1)[1].split(END, 1)[0].strip("\n") + "\n"


def render(name: str, values: dict) -> str:
    t = template(name)
    t = COND.sub(lambda m: m.group(2) if values.get(m.group(1)) else "", t)
    missing = sorted({m for m in PH.findall(t) if m not in values})
    if missing:
        raise SystemExit("prompt %s: no value for %s" % (name, ", ".join(missing)))
    return PH.sub(lambda m: str(values[m.group(1)]), t)


def instruction(name: str, key: str, values: dict) -> str:
    """A follow-up instruction kept in a prompt file between
    <!-- BEGIN INSTRUCTION key --> and <!-- END INSTRUCTION key -->."""
    text = (PROMPTS / name).read_text(encoding="utf-8")
    b, e = "<!-- BEGIN INSTRUCTION %s -->" % key, "<!-- END INSTRUCTION %s -->" % key
    if b not in text:
        raise SystemExit("prompt file %s has no instruction %r" % (name, key))
    t = text.split(b, 1)[1].split(e, 1)[0].strip("\n")
    missing = sorted({m for m in PH.findall(t) if m not in values})
    if missing:
        raise SystemExit("instruction %s/%s: no value for %s" % (name, key, ", ".join(missing)))
    return PH.sub(lambda m: str(values[m.group(1)]), t)


def placeholders(name: str) -> list[str]:
    return sorted(set(PH.findall(template(name))))


def write(name: str, values: dict, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render(name, values), encoding="utf-8")
    return dest
