#!/usr/bin/env python3
"""Resolve Steam Auto Cloud Windows roots inside an Ullage Wine prefix.

This deliberately does not perform network I/O or modify Steam metadata.  It
is the path layer for Ullage's native Cloud mapping: native macOS Steam cannot
resolve WinAppData* roots, but the Windows game must see those files below its
Wine prefix.
"""

import argparse
from pathlib import Path


ROOTS = {
    "WinMyDocuments": ("Documents",),
    "WinAppDataLocal": ("AppData", "Local"),
    "WinAppDataLocalLow": ("AppData", "LocalLow"),
    "WinAppDataRoaming": ("AppData", "Roaming"),
    "WinSavedGames": ("Saved Games",),
    "WinProgramData": ("..", "ProgramData"),
}


def resolve(prefix, user, root, relative=""):
    """Return a normalized path below *prefix* for a Windows UFS root."""
    try:
        parts = ROOTS[root]
    except KeyError as exc:
        raise ValueError(f"unsupported Windows cloud root: {root}") from exc

    prefix_path = Path(prefix).expanduser().resolve()
    if root == "WinProgramData":
        base = prefix_path / "drive_c" / "ProgramData"
    else:
        base = prefix_path / "drive_c" / "users" / user / Path(*parts)

    clean_relative = relative.replace("\\", "/").lstrip("/")
    result = (base / clean_relative).resolve()
    if result != base and base not in result.parents:
        raise ValueError("cloud path escapes its Windows cloud root")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, help="Wine prefix directory")
    parser.add_argument("--user", required=True, help="Wine user directory name")
    parser.add_argument("--root", required=True, choices=sorted(ROOTS))
    parser.add_argument("--path", default="", help="UFS relative path")
    args = parser.parse_args()
    print(resolve(args.prefix, args.user, args.root, args.path))


if __name__ == "__main__":
    main()
