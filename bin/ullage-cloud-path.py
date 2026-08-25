#!/usr/bin/env python3
"""Resolve Steam Auto Cloud Windows roots inside an Ullage Wine prefix.

This deliberately does not perform network I/O or modify Steam metadata.  It
is the path layer for Ullage's native Cloud mapping: native macOS Steam must
watch the same files that the Windows game sees through its Wine prefix.
"""

import argparse
from pathlib import Path


ROOTS = {
    "WindowsHome": (),
    "WinMyDocuments": ("Documents",),
    "WinAppDataLocal": ("AppData", "Local"),
    "WinAppDataLocalLow": ("AppData", "LocalLow"),
    "WinAppDataRoaming": ("AppData", "Roaming"),
    "WinSavedGames": ("Saved Games",),
    "WinProgramData": ("..", "ProgramData"),
    "SteamCloudDocuments": None,
    "gameinstall": None,
}


def _component(value, label):
    value = str(value)
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"invalid {label} path component: {value!r}")
    return value


def resolve(
    prefix,
    user,
    root,
    relative="",
    install_dir=None,
    steam_account_name=None,
):
    """Return the normalized Windows path represented by a UFS root."""
    if root not in ROOTS:
        raise ValueError(f"unsupported Windows cloud root: {root}")

    user = _component(user, "Wine user")
    prefix_path = Path(prefix).expanduser().resolve()
    if root == "gameinstall":
        if not install_dir:
            raise ValueError(
                "gameinstall cloud root requires the Steam install directory"
            )
        base = Path(install_dir).expanduser().resolve()
    elif root == "SteamCloudDocuments":
        if not install_dir:
            raise ValueError(
                "SteamCloudDocuments root requires the Steam install directory"
            )
        if not steam_account_name:
            raise ValueError(
                "SteamCloudDocuments root requires the Steam account name"
            )
        account = _component(steam_account_name, "Steam account")
        game_name = _component(Path(install_dir).expanduser().name, "game")
        base = (
            prefix_path
            / "drive_c"
            / "users"
            / user
            / "Documents"
            / "Steam Cloud"
            / account
            / game_name
        )
    elif root == "WinProgramData":
        base = prefix_path / "drive_c" / "ProgramData"
    else:
        parts = ROOTS[root]
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
    parser.add_argument("--install-dir", help="Steam game install directory")
    parser.add_argument(
        "--steam-account-name", help="Steam login name for SteamCloudDocuments"
    )
    args = parser.parse_args()
    print(
        resolve(
            args.prefix,
            args.user,
            args.root,
            args.path,
            args.install_dir,
            args.steam_account_name,
        )
    )


if __name__ == "__main__":
    main()
