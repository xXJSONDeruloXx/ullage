#!/usr/bin/env python3
"""Exercise mapping health classification and atomic repair."""

import importlib.util
import json
import stat
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


APPINFO_TEST = load("ullage_appinfo_mapping_test", "tests/test_appinfo.py")
MODULE = load("ullage_mapping", "bin/ullage-mapping.py")


def write_appinfo(filename, executable, version):
    filename.write_bytes(APPINFO_TEST.make_appinfo(version, executable))


def fixture(base, executable, version):
    appinfo = base / "Steam" / "appcache" / "appinfo.vdf"
    appinfo.parent.mkdir(parents=True)
    write_appinfo(appinfo, executable, version)
    state_home = base / "state"
    state_file = state_home / "config" / "games" / "42.launch.json"
    config_file = state_home / "config" / "games" / "42.conf"
    launcher = state_home / "launchers" / "42.sh"
    state_file.parent.mkdir(parents=True)
    launcher.parent.mkdir(parents=True)
    config_file.write_text("APP_ID='42'\n", encoding="utf-8")
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    state_file.write_text(
        json.dumps(
            {"appid": 42, "entry": "0", "original": "Game.exe", "installed": "ullage.sh"}
        ),
        encoding="utf-8",
    )
    return appinfo, state_file, config_file, launcher, state_home


for version in (MODULE.APPINFO.APPINFO_28, MODULE.APPINFO.APPINFO_29):
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        appinfo, state, config, launcher, state_home = fixture(base, "ullage.sh", version)

        healthy = MODULE.inspect_mapping(appinfo, state, config, launcher)
        assert healthy["status"] == "healthy"
        assert healthy["actual"] == healthy["expected"] == "ullage.sh"

        write_appinfo(appinfo, "Game.exe", version)
        stale = MODULE.inspect_mapping(appinfo, state, config, launcher)
        assert stale["status"] == "stale"
        repaired = MODULE.repair_mapping(
            appinfo,
            state,
            config,
            launcher,
            state_home / "backups" / "appinfo",
            check_steam=False,
        )
        assert repaired["status"] == "healthy"
        assert Path(repaired["backup"]).exists()
        assert stat.S_IMODE(Path(repaired["backup"]).stat().st_mode) == 0o600

        write_appinfo(appinfo, "other.sh", version)
        foreign = MODULE.inspect_mapping(appinfo, state, config, launcher)
        assert foreign["status"] == "foreign"
        try:
            MODULE.repair_mapping(
                appinfo,
                state,
                config,
                launcher,
                state_home / "backups" / "appinfo",
                check_steam=False,
            )
        except MODULE.MappingError:
            pass
        else:
            raise AssertionError("foreign launch mapping was silently overwritten")
        assert MODULE.repair_mapping(
            appinfo,
            state,
            config,
            launcher,
            state_home / "backups" / "appinfo",
            force=True,
            check_steam=False,
        )["status"] == "healthy"

        launcher.unlink()
        assert MODULE.inspect_mapping(appinfo, state, config, launcher)["status"] == "broken"

with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    appinfo = base / "appinfo.vdf"
    appinfo.write_bytes(APPINFO_TEST.make_appinfo(MODULE.APPINFO.APPINFO_29))
    state = base / "missing.json"
    result = MODULE.inspect_mapping(appinfo, state, base / "config", base / "launcher")
    assert result["status"] == "missing"

print("mapping status/repair: ok")
