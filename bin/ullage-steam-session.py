#!/usr/bin/env python3
"""Safely stop and relaunch the native Steam client around metadata changes."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


class SteamSessionError(Exception):
    """The native Steam session could not reach a safe lifecycle boundary."""


def _processes() -> list[dict[str, str]]:
    result = subprocess.run(
        ["/bin/ps", "-axo", "pid=,ucomm=,args="],
        capture_output=True,
        text=True,
        check=False,
    )
    processes = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) < 2:
            continue
        processes.append(
            {
                "pid": fields[0],
                "name": fields[1],
                "command": fields[2] if len(fields) > 2 else fields[1],
            }
        )
    return processes


def _is_steam(process: dict[str, str]) -> bool:
    name = Path(process["name"]).name.casefold()
    command = process["command"].casefold()
    return name in {"steam_osx", "steam helper"} or any(
        marker in command
        for marker in (
            "/contents/macos/steam_osx",
            "/contents/frameworks/steam helper.app/contents/macos/steam helper",
        )
    )


def _steam_processes() -> list[dict[str, str]]:
    return [process for process in _processes() if _is_steam(process)]


def _bridge_running() -> bool:
    return any(
        "ullage-bridge" in process["command"]
        for process in _processes()
        if process["pid"] != str(os.getpid())
    )


def _wait_for(predicate, timeout: float, description: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise SteamSessionError(f"timed out waiting for {description}")


def stop(timeout: float = 30.0) -> dict:
    """Gracefully ask Steam to quit and wait until all client helpers exit."""

    if not _steam_processes():
        return {"was_running": False, "stopped": True}
    if _bridge_running():
        raise SteamSessionError(
            "an Ullage game session is active; stop the game before changing Steam metadata"
        )
    result = subprocess.run(
        ["/usr/bin/osascript", "-e", 'tell application "Steam" to quit'],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        _wait_for(lambda: not _steam_processes(), timeout, "native Steam to stop")
    except SteamSessionError as exc:
        detail = (result.stderr or result.stdout).strip()
        if detail:
            raise SteamSessionError(f"could not request a graceful Steam quit: {detail}") from exc
        raise
    return {"was_running": True, "stopped": True}


def start(steam_root: str | Path, timeout: float = 45.0) -> dict:
    """Start Steam and wait for its native UI helper and AppInfo reader."""

    steam_root = Path(steam_root).expanduser()
    log_file = steam_root / "logs" / "appinfo_log.txt"
    started_at = time.time_ns()
    try:
        log_before = log_file.stat().st_mtime_ns
    except OSError:
        log_before = 0
    result = subprocess.run(
        ["/usr/bin/open", "-a", "Steam"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SteamSessionError(f"could not start native Steam{': ' + detail if detail else ''}")
    _wait_for(
        lambda: any(Path(process["name"]).name.casefold() == "steam_osx" for process in _steam_processes()),
        timeout,
        "native Steam to start",
    )
    _wait_for(
        lambda: any(
            "steam helper.app/contents/macos/steam helper" in process["command"].casefold()
            for process in _steam_processes()
        ),
        timeout,
        "Steam Helper to start",
    )

    def appinfo_loaded() -> bool:
        try:
            if log_file.stat().st_mtime_ns <= max(log_before, started_at):
                return False
            tail = log_file.read_text(encoding="utf-8", errors="replace")[-8192:]
        except OSError:
            return False
        return "ThreadedReadFromDisk: loading appinfo cache" in tail

    _wait_for(appinfo_loaded, timeout, "Steam to load appinfo.vdf")
    steam = _steam_processes()
    return {
        "started": True,
        "ready": True,
        "pids": [int(process["pid"]) for process in steam if process["pid"].isdigit()],
        "appinfo_loaded": True,
        "steam_helper": True,
    }


def restart(steam_root: str | Path, timeout: float = 45.0) -> dict:
    stopped = stop(timeout=timeout)
    started = start(steam_root, timeout=timeout)
    return {"stopped": stopped, "started": started, "restarted": stopped["was_running"]}
