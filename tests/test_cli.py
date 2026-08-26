#!/usr/bin/env python3
"""Exercise the versioned ullagectl facade with a disposable Steam library."""

import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "ullagectl"
APPINFO_TEST = ROOT / "tests" / "test_appinfo.py"
SPEC = importlib.util.spec_from_file_location("test_appinfo_helpers", APPINFO_TEST)
assert SPEC is not None and SPEC.loader is not None
APPINFO_HELPERS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APPINFO_HELPERS)


def run_cli(*arguments, env=None):
    command_environment = None
    if env:
        command_environment = dict(os.environ)
        command_environment.update(env)
    result = subprocess.run(
        [str(CLI), *arguments, "--json"],
        capture_output=True,
        text=True,
        check=False,
        env=command_environment,
    )
    assert result.stdout, result.stderr
    return result.returncode, json.loads(result.stdout)


def make_fixture():
    directory = tempfile.TemporaryDirectory()
    root = Path(directory.name)
    steam = root / "Steam"
    install = steam / "steamapps/common/Example"
    install.mkdir(parents=True)
    (install / "Game.exe").write_bytes(b"MZ\0\0")
    (steam / "steamapps").mkdir(exist_ok=True)
    (steam / "steamapps/appmanifest_42.acf").write_text(
        '"AppState"\n{\n'
        '    "appid" "42"\n'
        '    "name" "Example Game"\n'
        '    "StateFlags" "4"\n'
        '    "installdir" "Example"\n'
        '}\n',
        encoding="utf-8",
    )
    (steam / "steamapps/libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n'
        '\t"0"\n\t{\n'
        f'\t\t"path"\t\t"{steam}"\n'
        '\t\t"apps"\n\t\t{\n\t\t\t"42"\t\t"1"\n\t\t}\n'
        '\t}\n'
        '\t"1"\n\t{\n'
        f'\t\t"path"\t\t"{root / "unavailable-library"}"\n'
        '\t\t"apps"\n\t\t{\n\t\t}\n'
        '\t}\n}\n',
        encoding="utf-8",
    )
    (steam / "appcache").mkdir()
    sections = {
        "appinfo": {
            "common": {"name": "Example Game", "type": "game", "oslist": "windows,macos"},
            "config": {
                "launch": {
                    "0": {"executable": "Game.exe", "description": "Play", "arguments": "-safe"},
                    "1": {"executable": "Missing.exe", "description": "Missing", "config": {"oslist": "windows"}},
                    "2": {"executable": "Example.app", "config": {"oslist": "macos"}},
                }
            },
        }
    }
    not_installed_sections = {
        "appinfo": {
            "common": {"name": "Not Installed Game", "type": "game", "oslist": "windows"},
            "config": {"launch": {"0": {"executable": "Game.exe"}}},
        }
    }
    version = APPINFO_HELPERS.MODULE.APPINFO_28
    records = []
    for appid, record_sections in ((42, sections), (77, not_installed_sections)):
        encoded = APPINFO_HELPERS.encode_v28_dict(record_sections)
        records.append(
            struct.pack(
                "<4IQ20sI20s",
                appid,
                len(encoded) + 68 - 8,
                0,
                0,
                0,
                b"\0" * 20,
                0,
                b"\0" * 20,
            )
            + encoded
        )
    (steam / "appcache/appinfo.vdf").write_bytes(
        struct.pack("<Q", version)
        + b"\0" * 8
        + b"".join(records)
        + b"\0" * 68
    )
    localconfig = steam / "userdata/123/config/localconfig.vdf"
    localconfig.parent.mkdir(parents=True)
    localconfig.write_text(
        '"UserLocalConfigStore"\n{\n'
        '\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n\t\t\t\t{\n\t\t\t\t\t"42"\n\t\t\t\t\t{\n\t\t\t\t\t}\n\t\t\t\t\t"77"\n\t\t\t\t\t{\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n',
        encoding="utf-8",
    )
    depot_config = steam / "Steam.AppBundle/Steam/Contents/MacOS/steam_dev.cfg"
    depot_config.parent.mkdir(parents=True)
    depot_config.write_text("# keep this setting\n", encoding="utf-8")
    state = root / "state"
    return directory, steam, state


def make_runtime_fixture():
    directory = tempfile.TemporaryDirectory()
    home = Path(directory.name) / "home"
    root = home / "Library/Application Support/com.gamemac.www/wine-engine"
    installation = root / "containers/wine_installations/10000073"
    base_prefix = root / "containers/base_containers/1"
    virtual_prefix = root / "containers/virtual_containers/2"
    gptk = root / "downloads/gptk-3.0-3"
    bridge = Path(directory.name) / "state/runtime/lsteamclient"
    for path in (
        installation / "bin/wine",
        installation / "bin/wineserver",
        gptk / "external/libd3dshared.dylib",
        bridge / "x86_64-unix/lsteamclient.so",
        bridge / "i386-windows/lsteamclient.dll",
        bridge / "x86_64-windows/lsteamclient.dll",
        bridge / "x86_64-windows/steamclient64.dll",
        base_prefix / "system.reg",
        virtual_prefix / "system.reg",
        virtual_prefix / ".gamehub/layer-manifests/layer.json",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    (root / "container/wine_installations.json").parent.mkdir(parents=True, exist_ok=True)
    (root / "container/wine_installations.json").write_text(
        json.dumps(
            {
                "wine_installations": {
                    "10000073": {
                        "name": "wine-proton_11.0",
                        "install_path": str(installation),
                        "architecture": "x86_64",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "container/wine_containers.json").write_text(
        json.dumps(
            {
                "containers": {
                    "1": {
                        "prefix_path": str(base_prefix),
                        "wine_installation_id": "10000073",
                        "architecture": "x86_64",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "container/wine_virtual_containers.json").write_text(
        json.dumps(
            {
                "virtual_containers": {
                    "2": {
                        "base_container_id": "1",
                        "prefix_path": str(virtual_prefix),
                        "name": "gamehub-2",
                        "architecture": "x86_64",
                        "graphics_stack_config": {"install_path": str(gptk)},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return directory, home, bridge


def main():
    directory, steam, state = make_fixture()
    try:
        context = ("--steam-root", str(steam), "--state-dir", str(state))

        code, capabilities = run_cli("capabilities")
        assert code == 0
        assert capabilities["api_version"] == 1
        assert "multi_launch" in capabilities["capabilities"]

        code, library = run_cli("library", *context)
        assert code == 0
        assert library["api_version"] == 1
        assert library["count"] == 1
        game = library["games"][0]
        assert (game["appid"], game["state"]) == (42, "available")
        assert game["windows_depot_present"]
        assert [option["entry"] for option in game["launch_options"]] == ["0", "1"]
        assert game["launch_options"][0]["usable"]
        assert not game["launch_options"][1]["usable"]
        assert library["not_installed_count"] == 1
        assert library["not_installed"][0]["state"] == "not_installed"
        assert library["not_installed"][0]["appid"] == 77
        assert library["not_installed"][0]["source"] == "steam-appinfo-cache"

        code, depot = run_cli("steam", "set-depot-mode", "windows", *context)
        assert code == 0
        assert depot["mode"] == "windows"
        assert depot["steam"]["windows_depot_configured"]
        assert "@sSteamCmdForcePlatformType windows" in (
            steam / "Steam.AppBundle/Steam/Contents/MacOS/steam_dev.cfg"
        ).read_text(encoding="utf-8")

        code, depot = run_cli("steam", "set-depot-mode", "native", *context)
        assert code == 0
        assert depot["mode"] == "native"
        assert "@sSteamCmdForcePlatformType windows" not in (
            steam / "Steam.AppBundle/Steam/Contents/MacOS/steam_dev.cfg"
        ).read_text(encoding="utf-8")

        code, plan = run_cli("plan", "42", *context)
        assert code == 0
        assert plan["plan"]["ready"]
        assert plan["plan"]["launches"][0]["action"] == "map"
        assert plan["plan"]["launches"][1]["action"] == "disable"
        assert plan["plan"]["requires_steam_stopped"]

        code, missing = run_cli("inspect", "999", *context)
        assert code != 0
        assert missing["api_version"] == 1
        assert missing["ok"] is False
        assert missing["error"]["code"] == "not_installed"

        runtime_directory, runtime_home, runtime_bridge = make_runtime_fixture()
        try:
            runtime_context = (
                "--steam-root",
                str(runtime_home / "Steam"),
                "--state-dir",
                str(runtime_bridge.parents[1]),
            )
            code, runtimes = run_cli(
                "runtime",
                "list",
                *runtime_context,
                env={"HOME": str(runtime_home)},
            )
            assert code == 0
            assert runtimes["count"] == 1
            runtime = runtimes["runtimes"][0]
            assert runtime["id"] == "gamehub-container-2"
            assert runtime["status"] == "ready"
            assert runtime["wine_root"] == str(runtime_home / "Library/Application Support/com.gamemac.www/wine-engine/containers/wine_installations/10000073")
            assert runtime["prefix_base"] == str(runtime_home / "Library/Application Support/com.gamemac.www/wine-engine/containers/base_containers/1")
        finally:
            runtime_directory.cleanup()

        print("ullagectl facade: ok")
    finally:
        directory.cleanup()


if __name__ == "__main__":
    sys.exit(main())
