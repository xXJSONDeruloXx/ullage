"""Exercise restart-aware metadata reconciliation without a live Steam client."""

import contextlib
import importlib.util
import importlib.machinery
import io
import json
import tempfile
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    if path.name == "ullage":
        loader = importlib.machinery.SourceFileLoader(name, str(path))
        spec = importlib.util.spec_from_loader(name, loader)
    else:
        spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


APPINFO_TEST = load("metadata_appinfo_test", ROOT / "tests" / "test_appinfo.py")
ULLAGE = load("metadata_ullage", ROOT / "bin" / "ullage")


def args(steam_root, state_root, command="status", restart_steam=False):
    return Namespace(
        appid_pos=42,
        appid_option=None,
        steam_root=str(steam_root),
        state_dir=str(state_root),
        metadata_command=command,
        force=False,
        restart_steam=restart_steam,
    )


with tempfile.TemporaryDirectory(prefix="ullage-metadata.") as directory:
    root = Path(directory)
    steam = root / "Steam"
    appinfo_file = steam / "appcache" / "appinfo.vdf"
    appinfo_file.parent.mkdir(parents=True)
    install = steam / "steamapps" / "common" / "Example"
    install.mkdir(parents=True)
    original = APPINFO_TEST.make_appinfo(
        APPINFO_TEST.MODULE.APPINFO_29,
        sections={
            "appinfo": {
                "common": {"oslist": "windows"},
                "config": {"launch": {"0": {"executable": "Game.exe"}}},
            }
        },
    )
    appinfo_file.write_bytes(original)

    state_root = root / "state"
    config_dir = state_root / "config" / "games"
    launcher = state_root / "launchers" / "42.sh"
    config_dir.mkdir(parents=True)
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    (config_dir / "42.conf").write_text("APP_ID='42'\n", encoding="utf-8")
    state = {
        "appid": 42,
        "entry": "0",
        "original": "Game.exe",
        "installed": "../../../../../../state/launchers/42.sh",
        "launcher": str(launcher),
    }
    (config_dir / "42.launch.json").write_text(json.dumps(state), encoding="utf-8")
    patched = APPINFO_TEST.MODULE.AppInfo(appinfo_file)
    patched.replace_launch(42, state["installed"])
    patched.write(appinfo_file)

    metadata = ULLAGE.metadata_record(args(steam, state_root), 42)
    assert metadata["mapping_status"] == "healthy"
    assert metadata["action"] == "noop"
    assert metadata["restart_required"] is False
    assert metadata["requires_steam_stopped"] is False

    original_steam_running = ULLAGE.steam_running
    ULLAGE.steam_running = lambda: (_ for _ in ()).throw(
        AssertionError("healthy repair must not inspect Steam state")
    )
    try:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert ULLAGE.command_repair(args(steam, state_root, "repair")) == 0
        payload = json.loads(output.getvalue())
        assert payload["changed"] is False
        assert payload["restart_required"] is False
    finally:
        ULLAGE.steam_running = original_steam_running

    restored = APPINFO_TEST.MODULE.AppInfo(appinfo_file)
    restored.replace_launch(42, "Game.exe", expect=state["installed"])
    restored.write(appinfo_file)
    ULLAGE.steam_running = lambda: True
    try:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert ULLAGE.command_metadata(args(steam, state_root, "reconcile")) == 1
        payload = json.loads(output.getvalue())
        assert payload["error"]["code"] == "steam_running"
    finally:
        ULLAGE.steam_running = original_steam_running

    ULLAGE.steam_running = lambda: False
    try:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert ULLAGE.command_metadata(args(steam, state_root, "reconcile")) == 0
        payload = json.loads(output.getvalue())
        assert payload["changed"] is True
        assert payload["restart_required"] is True
        assert payload["mapping"]["status"] == "healthy"
        assert Path(payload["mapping"]["appinfo"]).read_bytes() != original
        assert list((state_root / "backups" / "appinfo").glob("42-repair-*.vdf"))
    finally:
        ULLAGE.steam_running = original_steam_running

    restored = APPINFO_TEST.MODULE.AppInfo(appinfo_file)
    restored.replace_launch(42, "Game.exe", expect=state["installed"])
    restored.write(appinfo_file)

    class FakeSteamSession:
        def __init__(self):
            self.stopped = 0
            self.started = 0

        def stop(self):
            self.stopped += 1
            return {"was_running": True, "stopped": True}

        def start(self, steam_root):
            self.started += 1
            return {
                "started": True,
                "ready": True,
                "appinfo_loaded": True,
                "steam_helper": True,
                "pids": [101],
            }

    original_session = ULLAGE.STEAM_SESSION
    fake_session = FakeSteamSession()
    ULLAGE.STEAM_SESSION = fake_session
    try:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert ULLAGE.command_metadata(args(steam, state_root, "reconcile", True)) == 0
        payload = json.loads(output.getvalue())
        assert payload["changed"] is True
        assert payload["mapping_status"] == "healthy"
        assert payload["restart_required"] is False
        assert payload["requires_steam_stopped"] is False
        assert payload["steam_session"]["started"]["ready"] is True
        assert fake_session.stopped == 1
        assert fake_session.started == 1
    finally:
        ULLAGE.STEAM_SESSION = original_session

print("metadata reconciliation: ok")
