#!/usr/bin/env python3
"""Exercise Steam redirect paths for flat and nested Windows depots."""

import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin" / "ullage-path.py"
SPEC = importlib.util.spec_from_file_location("ullage_path", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    library = base / "Library" / "Steam" / "steamapps" / "common"
    flat_install = library / "Katamari Damacy REROLL"
    nested_install = library / "JellyCar Worlds"
    nested_executable = nested_install / "windows" / "JellyCar Worlds.exe"
    launcher = base / ".ullage" / "launchers" / "1740930.sh"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")

    flat_relative = MODULE.relative_path(flat_install, launcher)
    nested_relative = MODULE.relative_path(nested_install, launcher)
    wrong_relative = MODULE.relative_path(nested_executable.parent, launcher)

    assert (flat_install / flat_relative).resolve() == launcher.resolve()
    assert (nested_install / nested_relative).resolve() == launcher.resolve()
    assert nested_relative != wrong_relative
    assert ".ullage/launchers/1740930.sh" in nested_relative
    assert "/" in nested_relative

print("Steam redirect paths: ok")
