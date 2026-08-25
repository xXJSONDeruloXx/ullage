#!/usr/bin/env python3
"""Exercise native Cloud override and symlink ownership semantics."""

import importlib.util
import hashlib
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


APPINFO_TEST = load("ullage_appinfo_test", "tests/test_appinfo.py")
MODULE = load("ullage_cloud_native", "bin/ullage-cloud-native.py")

assert MODULE.normalize_addpath_root("/Ullage/") == "Ullage"
try:
    MODULE.normalize_addpath_root("../outside")
except MODULE.NativeCloudError:
    pass
else:
    raise AssertionError("unsafe native Cloud addpath was accepted")


def sections():
    return {
        "appinfo": {
            "config": {"launch": {"0": {"executable": "Game.exe"}}},
            "ufs": {
                "savefiles": {
                    "0": {
                        "root": "WinAppDataLocalLow",
                        "path": "Example/{64BitSteamID}",
                        "pattern": "*",
                    }
                },
                "rootoverrides": {
                    "0": {
                        "root": "WinAppDataLocalLow",
                        "os": "MacOS",
                        "oscompare": "=",
                        "useinstead": "MacAppSupport",
                        "addpath": "example.native",
                    }
                },
            },
        }
    }


def sonic_sections():
    return {
        "appinfo": {
            "config": {"launch": {"0": {"executable": "Game.exe"}}},
            "ufs": {
                "savefiles": {
                    "0": {
                        "root": "WinAppDataLocal",
                        "path": "",
                        "pattern": "*.bin",
                    }
                }
            },
        }
    }


for version in (MODULE.APPINFO.APPINFO_28, MODULE.APPINFO.APPINFO_29):
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        appinfo_file = base / "appinfo.vdf"
        appinfo_file.write_bytes(APPINFO_TEST.make_appinfo(version, sections=sections()))
        prefix = base / "prefix"
        prefix.mkdir()
        (prefix / "system.reg").write_text("", encoding="utf-8")
        (prefix / "user.reg").write_text(
            '"USERPROFILE"="C:\\\\users\\\\steamuser"\n', encoding="utf-8"
        )
        state_file = base / "state.json"
        native_base = base / "Application Support"

        state = MODULE.install(
            appinfo_file,
            42,
            prefix,
            "auto",
            native_base,
            "Ullage",
            "Windows",
            state_file,
        )
        assert state["user"] == "steamuser"
        entry = state["entries"][0]
        assert entry["key"] == "1"
        assert entry["original"] is None
        assert Path(entry["link"]).is_symlink()
        assert Path(entry["link"]).resolve() == Path(entry["target"])

        patched = MODULE.APPINFO.AppInfo(appinfo_file)
        override = patched.records[42].sections["appinfo"]["ufs"]["rootoverrides"]["1"]
        assert override == MODULE.override_for(
            "WinAppDataLocalLow", "Windows", "Ullage/42"
        )

        MODULE.restore(appinfo_file, state_file)
        restored = MODULE.APPINFO.AppInfo(appinfo_file)
        overrides = restored.records[42].sections["appinfo"]["ufs"]["rootoverrides"]
        assert "1" not in overrides
        assert overrides["0"]["os"] == "MacOS"
        assert not Path(entry["link"]).exists()


for version in (MODULE.APPINFO.APPINFO_28, MODULE.APPINFO.APPINFO_29):
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        appinfo_file = base / "appinfo.vdf"
        appinfo_file.write_bytes(APPINFO_TEST.make_appinfo(version, sections=sonic_sections()))
        prefix = base / "prefix"
        prefix.mkdir()
        (prefix / "system.reg").write_text("", encoding="utf-8")
        (prefix / "user.reg").write_text(
            '"USERPROFILE"="C:\\\\users\\\\steamuser"\n', encoding="utf-8"
        )
        steam_root = base / "Steam"
        remote = steam_root / "userdata" / "123" / "42" / "remote"
        remote.mkdir(parents=True)
        payload = b"native-cache-seed"
        remote_file = remote / "SaveData.bin"
        remote_file.write_bytes(payload)
        cache = remote.parent / "remotecache.vdf"
        cache.write_text(
            '"42"\n'
            "{\n"
            '\t"ChangeNumber"\t"1"\n'
            '\t"OSType"\t"0"\n'
            '\t"SaveData.bin"\n'
            "\t{\n"
            f'\t\t"size"\t"{len(payload)}"\n'
            f'\t\t"sha"\t"{hashlib.sha1(payload).hexdigest()}"\n'
            "\t}\n"
            "}\n",
            encoding="utf-8",
        )
        state_file = base / "state.json"
        state = MODULE.install(
            appinfo_file,
            42,
            prefix,
            "auto",
            base / "Application Support",
            "Ullage",
            "Windows",
            state_file,
            steam_root,
        )
        seeded = prefix / "drive_c/users/steamuser/AppData/Local/SaveData.bin"
        assert seeded.read_bytes() == payload
        assert [Path(item).resolve() for item in state["seeded_files"]] == [
            seeded.resolve()
        ]

print("native cloud overrides: ok")
