"""Exercise the explicit user-owned Windows Steam client import path."""

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "test_steam_client_helpers", ROOT / "bin" / "ullage-steam-client.py"
)
assert SPEC is not None and SPEC.loader is not None
STEAM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STEAM)


with tempfile.TemporaryDirectory(prefix="ullage-steam-client.") as directory:
    root = Path(directory)
    source = root / "steam-client"
    source.mkdir()
    for name in STEAM.ARCH_FILES["win64"]:
        (source / name).write_bytes(name.encode("ascii"))

    prefix = root / "prefix"
    (prefix / "drive_c").mkdir(parents=True)
    (prefix / "system.reg").write_text("registry\n", encoding="utf-8")
    manifest = root / "state/steam-client.json"

    inspected = STEAM.inspect_root(source, "win64")
    assert inspected["kind"] == "user-owned-steam-client"
    assert [item["path"] for item in inspected["files"]] == list(STEAM.ARCH_FILES["win64"])

    staged = STEAM.stage(source, prefix, "win64", manifest)
    assert manifest.is_file()
    assert json.loads(manifest.read_text(encoding="utf-8"))["architecture"] == "win64"
    assert all(item["action"] == "staged" for item in staged["staged"])

    replacement = source / "tier0_s64.dll"
    replacement.write_bytes(b"replacement")
    second = STEAM.stage(source, prefix, "win64")
    changed = next(item for item in second["staged"] if item["path"] == "tier0_s64.dll")
    assert changed["action"] == "staged"
    assert changed["backup"] is not None
    assert Path(changed["backup"]).read_bytes() == b"tier0_s64.dll"

print("Steam client import verification: ok")
