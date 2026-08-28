"""Exercise the native Steam lifecycle guard without touching a live client."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "steam_session_test", ROOT / "bin" / "ullage-steam-session.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


assert MODULE._is_steam({"name": "steam_osx", "command": "steam_osx"})
assert MODULE._is_steam(
    {
        "name": "Steam",
        "command": "/Applications/Steam.app/Contents/Frameworks/Steam Helper.app/Contents/MacOS/Steam Helper",
    }
)
assert not MODULE._is_steam({"name": "Steam", "command": "/usr/bin/other"})

MODULE._processes = lambda: []
assert MODULE.stop() == {"was_running": False, "stopped": True}

MODULE._processes = lambda: [
    {"pid": "123", "name": "ullage-bridge", "command": "/tmp/ullage-bridge"},
]
assert MODULE._bridge_running()

print("Steam session guard: ok")
