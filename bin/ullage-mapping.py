#!/usr/bin/env python3
"""Inspect and repair one Ullage launch mapping."""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


APPINFO_PATH = Path(__file__).with_name("ullage-appinfo.py")
SPEC = importlib.util.spec_from_file_location("ullage_appinfo", APPINFO_PATH)
APPINFO = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(APPINFO)


class MappingError(Exception):
    """A mapping cannot be inspected or safely repaired."""


def _paths(state_home, appid):
    state_home = Path(state_home).expanduser()
    config_dir = state_home / "config" / "games"
    return {
        "state_file": config_dir / f"{appid}.launch.json",
        "config_file": config_dir / f"{appid}.conf",
        "launcher": state_home / "launchers" / f"{appid}.sh",
    }


def _launch_entries(appinfo, appid):
    try:
        return appinfo.records[appid].sections["appinfo"]["config"]["launch"]
    except (KeyError, TypeError) as exc:
        raise MappingError(f"AppID {appid} has no config/launch section") from exc


def _state_values(state, state_file):
    required = ("appid", "entry", "original", "installed")
    if any(key not in state for key in required):
        raise MappingError(f"mapping state is incomplete: {state_file}")
    try:
        appid = int(state["appid"])
    except (TypeError, ValueError) as exc:
        raise MappingError(f"mapping state has an invalid AppID: {state_file}") from exc
    if appid <= 0 or not isinstance(state["entry"], str):
        raise MappingError(f"mapping state has invalid launch metadata: {state_file}")
    if not isinstance(state["installed"], str) or not isinstance(state["original"], str):
        raise MappingError(f"mapping state has invalid executable values: {state_file}")
    return appid


def inspect_mapping(appinfo_file, state_file, config_file, launcher):
    """Return a JSON-friendly mapping health record."""

    appinfo_file = Path(appinfo_file).expanduser()
    state_file = Path(state_file).expanduser()
    config_file = Path(config_file).expanduser()
    launcher = Path(launcher).expanduser()
    result = {
        "appinfo": str(appinfo_file),
        "state_file": str(state_file),
        "config_file": str(config_file),
        "launcher": str(launcher),
    }
    if not state_file.is_file():
        result.update(status="missing", reason="launch state is missing")
        return result

    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        appid = _state_values(state, state_file)
    except (OSError, json.JSONDecodeError, MappingError) as exc:
        result.update(status="invalid", reason=str(exc))
        return result

    result.update(
        appid=appid,
        entry=state["entry"],
        expected=state["installed"],
        original=state["original"],
    )
    if not appinfo_file.is_file():
        result.update(status="unavailable", reason="appinfo.vdf is missing")
        return result

    try:
        appinfo = APPINFO.AppInfo(appinfo_file)
        entries = _launch_entries(appinfo, appid)
        current = entries.get(str(state["entry"]), {}).get("executable")
    except (OSError, APPINFO.AppInfoError, MappingError, AttributeError) as exc:
        result.update(status="unavailable", reason=str(exc))
        return result

    result["actual"] = current
    if not isinstance(current, str):
        result.update(status="stale", reason="recorded launch entry is missing")
        return result
    if current == state["installed"]:
        missing = []
        if not config_file.is_file():
            missing.append("config")
        if not launcher.is_file() or launcher.is_symlink():
            missing.append("launcher")
        if missing:
            result.update(
                status="broken",
                reason="generated " + ", ".join(missing) + " is missing or invalid",
            )
        else:
            result.update(status="healthy", reason="appinfo and generated state agree")
    elif current == state["original"]:
        result.update(status="stale", reason="Steam rewrote the launch entry")
    else:
        result.update(status="foreign", reason="launch entry changed outside Ullage")
    return result


def _steam_pids():
    pgrep = shutil.which("pgrep")
    if not pgrep:
        return []
    result = subprocess.run(
        [pgrep, "-x", "steam_osx"], capture_output=True, text=True, check=False
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def repair_mapping(
    appinfo_file,
    state_file,
    config_file,
    launcher,
    backup_dir,
    force=False,
    check_steam=True,
):
    """Reapply a recorded mapping atomically after Steam rewrites appinfo."""

    info = inspect_mapping(appinfo_file, state_file, config_file, launcher)
    if info["status"] == "healthy":
        return info
    if info["status"] != "stale" and not (force and info["status"] == "foreign"):
        raise MappingError(f"cannot repair mapping: {info.get('reason', info['status'])}")
    if (
        not Path(config_file).is_file()
        or not Path(launcher).is_file()
        or Path(launcher).is_symlink()
    ):
        raise MappingError("cannot repair mapping: generated config or launcher is missing")
    if check_steam:
        pids = _steam_pids()
        if pids:
            raise MappingError(
                "native Steam must be fully quit before repair (PIDs: %s)" % " ".join(pids)
            )

    appinfo_file = Path(appinfo_file).expanduser()
    backup_dir = Path(backup_dir).expanduser()
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S") + f".{time.time_ns()}"
    backup = backup_dir / f"{info['appid']}-repair-{stamp}.{os.getpid()}.vdf"
    shutil.copy2(appinfo_file, backup)
    os.chmod(backup, 0o600)

    fd, temporary = tempfile.mkstemp(
        prefix=f".{info['appid']}.appinfo-repair.",
        suffix=".vdf",
        dir=appinfo_file.parent,
    )
    os.close(fd)
    try:
        shutil.copy2(appinfo_file, temporary)
        appinfo = APPINFO.AppInfo(temporary)
        appinfo.replace_launch(
            info["appid"],
            info["expected"],
            entry=info["entry"],
            expect=info.get("actual"),
        )
        appinfo.write(temporary)
        with open(temporary, "rb") as stream:
            os.fsync(stream.fileno())
        os.chmod(temporary, appinfo_file.stat().st_mode & 0o777)
        os.replace(temporary, appinfo_file)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass

    repaired = inspect_mapping(appinfo_file, state_file, config_file, launcher)
    repaired["backup"] = str(backup)
    return repaired


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    for operation in ("status", "repair"):
        command = subparsers.add_parser(operation)
        command.add_argument("--appid", required=True, type=int)
        command.add_argument("--steam-root", required=True)
        command.add_argument(
            "--state-dir",
            default=os.environ.get("ULLAGE_STATE_DIR", str(Path.home() / ".ullage")),
        )
        command.add_argument("--json", action="store_true", dest="as_json")
        if operation == "repair":
            command.add_argument("--force", action="store_true")
    return parser


def _paths_from_args(args):
    state_paths = _paths(args.state_dir, args.appid)
    return (
        Path(args.steam_root).expanduser() / "appcache" / "appinfo.vdf",
        state_paths["state_file"],
        state_paths["config_file"],
        state_paths["launcher"],
        Path(args.state_dir).expanduser() / "backups" / "appinfo",
    )


def _print_result(result, as_json):
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    for key, value in result.items():
        print(f"{key}={value}")


def main(argv=None):
    args = _parser().parse_args(argv)
    appinfo, state, config, launcher, backup_dir = _paths_from_args(args)
    try:
        if args.operation == "status":
            result = inspect_mapping(appinfo, state, config, launcher)
        else:
            result = repair_mapping(
                appinfo,
                state,
                config,
                launcher,
                backup_dir,
                force=args.force,
            )
    except (MappingError, OSError, ValueError, APPINFO.AppInfoError) as exc:
        print(f"ullage-mapping: {exc}", file=sys.stderr)
        return 2
    _print_result(result, args.as_json)
    return 0 if result.get("status") == "healthy" else 1


if __name__ == "__main__":
    sys.exit(main())
