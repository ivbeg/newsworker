"""Every command-line option appears on its command's documentation page."""

import os
from pathlib import Path

import typer.main

from newsworker.core import app

DOCS = Path(__file__).resolve().parents[1] / "docs" / "docs"


def _commands(command, prefix=""):
    if hasattr(command, "commands"):
        for name, sub in command.commands.items():
            yield from _commands(sub, f"{prefix} {name}".strip())
    else:
        yield prefix, command


def test_every_option_is_documented():
    missing = []
    for name, command in _commands(typer.main.get_command(app)):
        top = name.split()[0]
        page = DOCS / ("integrations/mcp.md" if top == "mcp" else f"commands/{top}.md")
        assert os.path.exists(page), f"no documentation page for `{name}`"
        text = page.read_text(encoding="utf-8")
        for param in command.params:
            for option in getattr(param, "opts", []):
                if option.startswith("--") and option != "--help" and option not in text:
                    missing.append(f"{name} {option}")
    assert not missing, "Undocumented options: " + ", ".join(missing)
