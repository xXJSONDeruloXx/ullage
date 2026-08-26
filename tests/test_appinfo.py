#!/usr/bin/env python3
"""Exercise appinfo launch patch/restore without a Steam installation."""

import importlib.util
import struct
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin" / "ullage-appinfo.py"
SPEC = importlib.util.spec_from_file_location("ullage_appinfo", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def encode_v28_dict(value):
    output = bytearray()
    for key, item in value.items():
        output.append(0 if isinstance(item, dict) else 1)
        output.extend(key.encode("utf-8"))
        output.append(0)
        if isinstance(item, dict):
            output.extend(encode_v28_dict(item))
        else:
            output.extend(item.encode("utf-8"))
            output.append(0)
    output.append(8)
    return bytes(output)


def encode_v29_dict(value, pool):
    output = bytearray()
    for key, item in value.items():
        output.append(0 if isinstance(item, dict) else 1)
        output.extend(struct.pack("<I", pool.index(key)))
        if isinstance(item, dict):
            output.extend(encode_v29_dict(item, pool))
        else:
            output.extend(item.encode("utf-8"))
            output.append(0)
    output.append(8)
    return bytes(output)


def make_appinfo(version, executable="Game.exe", sections=None):
    if sections is None:
        sections = {
            "appinfo": {
                "config": {
                    "launch": {
                        "0": {"executable": executable},
                    }
                }
            }
        }
    if version == MODULE.APPINFO_28:
        encoded = encode_v28_dict(sections)
        offset = 16
        prefix = struct.pack("<Q", version) + b"\0" * 8
        pool = b""
    else:
        pool = []

        def collect_keys(value):
            for key, item in value.items():
                if key not in pool:
                    pool.append(key)
                if isinstance(item, dict):
                    collect_keys(item)

        collect_keys(sections)
        encoded = encode_v29_dict(sections, pool)
        offset = 16 + 68 + len(encoded) + 68
        prefix = struct.pack("<Qq", version, offset)

    header = struct.pack(
        "<4IQ20sI20s",
        42,
        len(encoded) + 68 - 8,
        0,
        0,
        0,
        b"\0" * 20,
        0,
        b"\0" * 20,
    )
    terminator = b"\0" * 68
    if version == MODULE.APPINFO_29:
        string_table = struct.pack("<I", len(pool))
        string_table += b"".join(item.encode("utf-8") + b"\0" for item in pool)
    else:
        string_table = b""
    return prefix + header + encoded + terminator + string_table


def exercise(version):
    with tempfile.TemporaryDirectory() as directory:
        filename = Path(directory) / "appinfo.vdf"
        filename.write_bytes(make_appinfo(version))

        appinfo = MODULE.AppInfo(filename)
        entry, original = appinfo.replace_launch(
            42, "../../ullage.sh", match="Game.exe"
        )
        assert entry == "0"
        assert original == "Game.exe"
        appinfo.write(filename)

        restored = MODULE.AppInfo(filename)
        entry, current, changed = restored.restore_launch(
            42, "Game.exe", "0", "../../ullage.sh"
        )
        assert (entry, current, changed) == ("0", "../../ullage.sh", True)
        restored.write(filename)

        before = filename.read_bytes()
        already_restored = MODULE.AppInfo(filename)
        entry, current, changed = already_restored.restore_launch(
            42, "Game.exe", "0", "../../ullage.sh"
        )
        assert (entry, current, changed) == ("0", "Game.exe", False)
        assert filename.read_bytes() == before


def main():
    for appinfo_version in (MODULE.APPINFO_28, MODULE.APPINFO_29):
        exercise(appinfo_version)

    for appinfo_version in (MODULE.APPINFO_28, MODULE.APPINFO_29):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "appinfo.vdf"
            filename.write_bytes(
                make_appinfo(appinfo_version, "windows\\JellyCar Worlds.exe")
            )
            appinfo = MODULE.AppInfo(filename)
            entry, original = appinfo.replace_launch(
                42, "ullage-launcher", match="JellyCar Worlds.exe"
            )
            assert entry == "0"
            assert original == "windows\\JellyCar Worlds.exe"

    for appinfo_version in (MODULE.APPINFO_28, MODULE.APPINFO_29):
        sections = {
            "appinfo": {
                "common": {"oslist": "windows,macos"},
                "config": {
                    "launch": {
                        "0": {"executable": "Game.exe"},
                        "1": {
                            "executable": "Game-dx9.exe",
                            "config": {"oslist": "windows"},
                        },
                        "2": {
                            "executable": "Game.app",
                            "config": {"oslist": "macos"},
                        },
                    }
                },
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "appinfo.vdf"
            filename.write_bytes(make_appinfo(appinfo_version, sections=sections))
            appinfo = MODULE.AppInfo(filename)
            launches = appinfo.windows_launches(42)
            assert [item["entry"] for item in launches] == ["0", "1"]
            root = Path(directory) / "game"
            root.mkdir()
            (root / "Game.exe").write_bytes(b"pe")
            existing = appinfo.windows_launches(42, root)
            assert [item["entry"] for item in existing] == ["0"]
            changed = appinfo.replace_launches(
                42, [("0", "shim-0.sh"), ("1", "shim-1.sh")]
            )
            assert changed == [
                ("0", "Game.exe", "shim-0.sh"),
                ("1", "Game-dx9.exe", "shim-1.sh"),
            ]
            appinfo.write(filename)
            state = {
                "appid": 42,
                "entries": [
                    {
                        "entry": entry,
                        "original": original,
                        "installed": installed,
                    }
                    for entry, original, installed in changed
                ],
            }
            restored = MODULE.AppInfo(filename)
            results = restored.restore_state(state)
            assert [item[:3] for item in results] == [
                ("0", "shim-0.sh", True),
                ("1", "shim-1.sh", True),
            ]
            restored.write(filename)
            already_restored = MODULE.AppInfo(filename)
            results = already_restored.restore_state(state)
            assert [item[:3] for item in results] == [
                ("0", "Game.exe", False),
                ("1", "Game-dx9.exe", False),
            ]
            mismatched = dict(state, appid=43)
            try:
                already_restored.restore_state(mismatched, expected_appid=42)
            except MODULE.AppInfoError as exc:
                assert "does not match requested AppID" in str(exc)
            else:
                raise AssertionError("mismatched restore AppID was accepted")

    for appinfo_version in (MODULE.APPINFO_28, MODULE.APPINFO_29):
        sections = {
            "appinfo": {
                "common": {"oslist": "windows"},
                "config": {
                    "launch": {
                        "0": {"executable": "bin\\Game.exe", "workingdir": "bin"},
                        "1": {"executable": "..\\outside.exe", "workingdir": ".."},
                        "2": {"executable": "bin\\Game2.exe", "workingdir": ".."},
                        "3": {"executable": "C:\\outside.exe", "workingdir": "bin"},
                        "4": {"executable": "/tmp/outside.exe", "workingdir": "bin"},
                        "5": {"executable": "bin\\Link.exe", "workingdir": "bin"},
                        "../escape": {"executable": "bin\\Game.exe", "workingdir": "bin"},
                    }
                },
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "install"
            (root / "bin").mkdir(parents=True)
            (root / "bin" / "Game.exe").write_bytes(b"pe")
            (root / "bin" / "Game2.exe").write_bytes(b"pe")
            (Path(directory) / "outside.exe").write_bytes(b"pe")
            (root / "bin" / "Link.exe").symlink_to(root / "bin" / "Game.exe")
            filename = Path(directory) / "appinfo.vdf"
            filename.write_bytes(make_appinfo(appinfo_version, sections=sections))
            appinfo = MODULE.AppInfo(filename)
            launches = appinfo.windows_launches(42, root)
            assert launches == [
                {"entry": "0", "executable": "bin\\Game.exe", "workingdir": "bin"}
            ]

    print("appinfo patch/restore: ok")


if __name__ == "__main__":
    main()
