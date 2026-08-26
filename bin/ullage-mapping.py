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


def _state_entries(state, state_file, default_launcher):
    """Normalize legacy and multi-launch state into one internal shape."""
    try:
        appid = _state_values(state, state_file)
    except MappingError:
        entries = state.get("entries") if isinstance(state, dict) else None
        if not isinstance(entries, list) or not entries:
            raise
        try:
            appid = int(state["appid"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MappingError(f"mapping state has an invalid AppID: {state_file}") from exc

    raw_entries = state.get("entries")
    if raw_entries is None:
        raw_entries = [state]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise MappingError(f"mapping state has no launch entries: {state_file}")

    entries = []
    for item in raw_entries:
        if not isinstance(item, dict):
            raise MappingError(f"mapping state has an invalid launch entry: {state_file}")
        required = ("entry", "original", "installed")
        if any(key not in item for key in required):
            raise MappingError(f"mapping state is incomplete: {state_file}")
        if not isinstance(item["entry"], str):
            raise MappingError(f"mapping state has invalid launch metadata: {state_file}")
        if not isinstance(item["original"], str) or not isinstance(item["installed"], str):
            raise MappingError(f"mapping state has invalid executable values: {state_file}")
        launcher = item.get("launcher") or str(default_launcher)
        entries.append(
            {
                "entry": item["entry"],
                "original": item["original"],
                "installed": item["installed"],
                "launcher": launcher,
            }
        )
    return appid, entries


def inspect_mapping(appinfo_file, state_file, config_file, launcher, expected_appid=None):
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
        appid, state_entries = _state_entries(state, state_file, launcher)
    except (OSError, json.JSONDecodeError, MappingError) as exc:
        result.update(status="invalid", reason=str(exc))
        return result

    result.update(appid=appid)
    if expected_appid is not None and appid != expected_appid:
        result.update(
            status="invalid",
            reason=f"mapping state AppID {appid} does not match requested AppID {expected_appid}",
        )
        return result
    if len(state_entries) == 1:
        result.update(
            entry=state_entries[0]["entry"],
            expected=state_entries[0]["installed"],
            original=state_entries[0]["original"],
        )
    if not appinfo_file.is_file():
        result.update(status="unavailable", reason="appinfo.vdf is missing")
        return result

    try:
        appinfo = APPINFO.AppInfo(appinfo_file)
        launch_entries = _launch_entries(appinfo, appid)
        inspected = []
        for item in state_entries:
            current = launch_entries.get(item["entry"], {}).get("executable")
            inspected.append({**item, "actual": current})
    except (OSError, APPINFO.AppInfoError, MappingError, AttributeError) as exc:
        result.update(status="unavailable", reason=str(exc))
        return result

    result["entries"] = inspected
    if len(inspected) == 1:
        result["actual"] = inspected[0]["actual"]
    statuses = []
    for item in inspected:
        current = item["actual"]
        if not isinstance(current, str):
            statuses.append("stale")
        elif current == item["installed"]:
            if not config_file.is_file() or not Path(item["launcher"]).is_file() or Path(
                item["launcher"]
            ).is_symlink():
                statuses.append("broken")
            else:
                statuses.append("healthy")
        elif current == item["original"]:
            statuses.append("stale")
        else:
            statuses.append("foreign")
    if "foreign" in statuses:
        result.update(status="foreign", reason="a launch entry changed outside Ullage")
    elif "stale" in statuses:
        result.update(status="stale", reason="Steam rewrote a launch entry")
    elif "broken" in statuses:
        result.update(status="broken", reason="generated config or launcher is missing")
    else:
        result.update(status="healthy", reason="appinfo and generated state agree")
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
    expected_appid=None,
):
    """Reapply a recorded mapping atomically after Steam rewrites appinfo."""

    info = inspect_mapping(
        appinfo_file, state_file, config_file, launcher, expected_appid=expected_appid
    )
    if info["status"] == "healthy":
        return info
    if info["status"] != "stale" and not (force and info["status"] == "foreign"):
        raise MappingError(f"cannot repair mapping: {info.get('reason', info['status'])}")
    if not Path(config_file).is_file():
        raise MappingError("cannot repair mapping: generated config or launcher is missing")
    for item in info.get("entries", []):
        path = Path(item["launcher"])
        if not path.is_file() or path.is_symlink():
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
        if len(info["entries"]) == 1:
            item = info["entries"][0]
            appinfo.replace_launch(
                info["appid"],
                item["installed"],
                entry=item["entry"],
                expect=item.get("actual"),
            )
        else:
            appinfo.replace_launches(
                info["appid"],
                [(item["entry"], item["installed"]) for item in info["entries"]],
                expects={item["entry"]: item.get("actual") for item in info["entries"]},
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

    repaired = inspect_mapping(
        appinfo_file, state_file, config_file, launcher, expected_appid=expected_appid
    )
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
            result = inspect_mapping(
                appinfo, state, config, launcher, expected_appid=args.appid
            )
        else:
            result = repair_mapping(
                appinfo,
                state,
                config,
                launcher,
                backup_dir,
                force=args.force,
                expected_appid=args.appid,
            )
    except (MappingError, OSError, ValueError, APPINFO.AppInfoError) as exc:
        print(f"ullage-mapping: {exc}", file=sys.stderr)
        return 2
    _print_result(result, args.as_json)
    return 0 if result.get("status") == "healthy" else 1


if __name__ == "__main__":
    sys.exit(main())
