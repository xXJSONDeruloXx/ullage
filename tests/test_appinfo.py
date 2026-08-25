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


def make_appinfo(version, executable="Game.exe"):
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
        pool = ["appinfo", "config", "launch", "0", "executable"]
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

        patched = MODULE.AppInfo(filename)
        entry, current = patched.replace_launch(
            42, "Game.exe", entry="0", expect="../../ullage.sh"
        )
        assert entry == "0"
        assert current == "../../ullage.sh"
        patched.write(filename)

        restored = MODULE.AppInfo(filename)
        assert (
            restored.records[42]
            .sections["appinfo"]["config"]["launch"]["0"]["executable"]
            == "Game.exe"
        )


for appinfo_version in (MODULE.APPINFO_28, MODULE.APPINFO_29):
    exercise(appinfo_version)


for appinfo_version in (MODULE.APPINFO_28, MODULE.APPINFO_29):
    with tempfile.TemporaryDirectory() as directory:
        filename = Path(directory) / "appinfo.vdf"
        filename.write_bytes(make_appinfo(appinfo_version, "windows\\JellyCar Worlds.exe"))
        appinfo = MODULE.AppInfo(filename)
        entry, original = appinfo.replace_launch(42, "ullage-launcher", match="JellyCar Worlds.exe")
        assert entry == "0"
        assert original == "windows\\JellyCar Worlds.exe"

print("appinfo patch/restore: ok")
