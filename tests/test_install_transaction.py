"""Exercise the installer and remover against a temporary Steam appcache."""

import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "test_appinfo.py"
SPEC = importlib.util.spec_from_file_location("test_appinfo", FIXTURE_PATH)
FIXTURE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(FIXTURE)


def write_pe(path):
    data = bytearray(0x400)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 1, 0, 0, 0, 0xF0, 0x2022)
    struct.pack_into("<HBBIII", data, 0x98, 0x20B, 14, 0, 0x200, 0x200, 0)
    struct.pack_into("<II", data, 0xA8, 0x1000, 0x1000)
    struct.pack_into("<Q", data, 0xB0, 0x140000000)
    struct.pack_into("<II", data, 0xB8, 0x1000, 0x200)
    struct.pack_into("<H", data, 0xC0, 6)
    struct.pack_into("<HH", data, 0xC4, 0, 0)
    struct.pack_into("<IIII", data, 0xC8, 0, 0x3000, 0x4000, 0)
    struct.pack_into("<HH", data, 0xD8, 0, 0)
    path.write_bytes(data)


def run(command):
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def appinfo_launches(path):
    appinfo = FIXTURE.MODULE.AppInfo(path)
    return appinfo.records[42].sections["appinfo"]["config"]["launch"]


def make_case(root, launches):
    steam = root / "Steam"
    install = steam / "steamapps" / "common" / "Multi"
    state = root / "state"
    prefix = root / "prefix"
    wine = root / "wine"
    gptk = root / "gptk"
    bridge = root / "bridge"
    for path in (
        steam / "appcache",
        steam / "Steam.AppBundle" / "Steam" / "Contents" / "MacOS",
        install / "bin",
        install / "tools",
        prefix / "drive_c" / "Program Files (x86)" / "Steam",
        wine / "bin",
        gptk / "external",
        bridge / "x86_64-unix",
        bridge / "x86_64-windows",
    ):
        path.mkdir(parents=True, exist_ok=True)

    write_pe(install / "bin" / "Game.exe")
    write_pe(install / "tools" / "Mode.exe")
    (steam / "appcache" / "appinfo.vdf").write_bytes(
        FIXTURE.make_appinfo(FIXTURE.MODULE.APPINFO_29, sections=launches)
    )
    for path in (wine / "bin" / "wine", wine / "bin" / "wineserver"):
        shutil.copyfile("/usr/bin/true", path)
        path.chmod(0o755)
    (gptk / "external" / "libd3dshared.dylib").touch()
    (steam / "Steam.AppBundle" / "Steam" / "Contents" / "MacOS" / "steamclient.dylib").touch()
    (bridge / "x86_64-unix" / "lsteamclient.so").touch()
    (bridge / "x86_64-windows" / "lsteamclient.dll").touch()
    forwarder = bridge / "x86_64-windows" / "steamclient64.dll"
    forwarder.touch()
    shutil.copyfile(
        forwarder,
        prefix / "drive_c" / "Program Files (x86)" / "Steam" / "steamclient64.dll",
    )
    (prefix / "system.reg").touch()
    return {
        "steam": steam,
        "install": install,
        "state": state,
        "prefix": prefix,
        "wine": wine,
        "gptk": gptk,
        "bridge": bridge,
    }


def install(case):
    install = case["install"]
    command = [
        str(ROOT / "bin" / "ullage-install"),
        "--appid",
        "42",
        "--target",
        str(install / "bin" / "Game.exe"),
        "--install-dir",
        str(install),
        "--prefix",
        str(case["prefix"]),
        "--steam-root",
        str(case["steam"]),
        "--wine-root",
        str(case["wine"]),
        "--gptk-root",
        str(case["gptk"]),
        "--bridge-root",
        str(case["bridge"]),
        "--state-dir",
        str(case["state"]),
    ]
    run(command)


def remove(case):
    run(
        [
            str(ROOT / "bin" / "ullage-remove"),
            "--appid",
            "42",
            "--steam-root",
            str(case["steam"]),
            "--state-dir",
            str(case["state"]),
        ]
    )


def exercise(launches, expected_launchers, expected_game_dirs):
    with tempfile.TemporaryDirectory(prefix="ullage-install-it.") as directory:
        case = make_case(Path(directory), launches)
        install(case)

        state_file = case["state"] / "config" / "games" / "42.launch.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert [entry["entry"] for entry in state["entries"]] == expected_launchers
        for entry, game_dir in zip(expected_launchers, expected_game_dirs):
            launcher = case["state"] / "launchers" / f"42-entry-{entry}.sh"
            if len(expected_launchers) == 1:
                launcher = case["state"] / "launchers" / "42.sh"
            text = launcher.read_text(encoding="utf-8")
            assert f"--game-dir '{case['install'] / game_dir}'" in text

        launch = appinfo_launches(case["steam"] / "appcache" / "appinfo.vdf")
        for entry in expected_launchers:
            assert launch[entry]["executable"].endswith(f"42-entry-{entry}.sh")
        remove(case)

        restored = appinfo_launches(case["steam"] / "appcache" / "appinfo.vdf")
        for entry, item in launches["appinfo"]["config"]["launch"].items():
            assert restored[entry].get("executable") == item.get("executable")
        assert not state_file.exists()


def main():
    steam_pids = subprocess.run(
        ["/usr/bin/pgrep", "-x", "steam_osx"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if steam_pids:
        raise SystemExit("quit native Steam before running: make integration")

    multi = {
        "appinfo": {
            "common": {"oslist": "windows"},
            "config": {
                "launch": {
                    "0": {"executable": "bin\\Game.exe", "workingdir": "bin"},
                    "1": {"executable": "tools\\Mode.exe", "workingdir": "tools"},
                    "2": {"executable": "missing.exe"},
                    "3": {"executable": "Game.app", "config": {"oslist": "macos"}},
                }
            },
        }
    }
    exercise(multi, ["0", "1"], ["bin", "tools"])

    single = {
        "appinfo": {
            "common": {"oslist": "windows"},
            "config": {
                "launch": {
                    "0": {"executable": "bin\\Game.exe", "workingdir": "bin"},
                }
            },
        }
    }
    with tempfile.TemporaryDirectory(prefix="ullage-install-single.") as directory:
        case = make_case(Path(directory), single)
        install(case)
        launcher = case["state"] / "launchers" / "42.sh"
        assert f"--game-dir '{case['install'] / 'bin'}'" in launcher.read_text(
            encoding="utf-8"
        )
        remove(case)

    print("installer transaction: ok")


if __name__ == "__main__":
    sys.exit(main())
