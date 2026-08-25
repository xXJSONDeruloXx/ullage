"""Exercise Cloud transfer integrity without contacting Steam."""

import hashlib
import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("ullage_cloud_sync", ROOT / "bin/ullage-cloud-sync.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

assert MODULE.steamid64_for_account("392297941") == "76561198352563669"

pattern = {"root": "WinAppDataLocalLow", "path": "{64BitSteamID}/save1"}
assert MODULE.steam_filename(pattern, "392297941", "76561198352563669") == (
    "%WinAppDataLocalLow%76561198352563669/save1"
)
destination = MODULE.safe_destination(
    Path("/tmp/ullage-test-prefix"),
    "kurt",
    "%WinAppDataLocalLow%76561198352563669/save1/save.dat",
    [pattern],
    "392297941",
    "76561198352563669",
)
assert destination == Path(
    "/tmp/ullage-test-prefix/drive_c/users/kurt/AppData/LocalLow"
    "/76561198352563669/save1/save.dat"
).resolve()

with tempfile.TemporaryDirectory() as temporary:
    prefix = Path(temporary)
    (prefix / "user.reg").write_text(
        '"USERPROFILE"="C:\\\\users\\\\steamuser"\n', encoding="utf-8"
    )
    assert MODULE.resolve_wine_user(prefix, "auto") == "steamuser"
    assert MODULE.resolve_wine_user(prefix, "explicit") == "explicit"

with tempfile.TemporaryDirectory() as temporary:
    base = Path(temporary)
    source = base / "source.bin"
    destination = base / "nested" / "save.bin"
    payload = b"Ullage cloud integrity test\n"
    source.write_bytes(payload)
    digest = hashlib.sha1(payload).hexdigest()

    MODULE.download_file(source.as_uri(), destination, digest, len(payload))
    assert destination.read_bytes() == payload
    assert not list(destination.parent.glob(".*.ullage-download"))

    destination.write_bytes(b"old")
    try:
        MODULE.download_file(source.as_uri(), destination, "0" * 40, len(payload))
    except RuntimeError:
        pass
    else:
        raise AssertionError("invalid Cloud SHA was accepted")
    assert destination.read_bytes() == b"old"

with tempfile.TemporaryDirectory() as temporary:
    destination = Path(temporary) / "save.dat"
    payload = b"cached Cloud payload"
    destination.write_bytes(payload)
    remote = {"size": "19 B", "timestamp": "today", "file_sha": ""}
    entry = {
        **MODULE.remote_cache_identity(remote),
        "local_sha": MODULE.sha1(destination),
    }
    assert MODULE.cache_hit(remote, destination, entry)
    assert not MODULE.cache_hit({**remote, "timestamp": "tomorrow"}, destination, entry)
    destination.write_bytes(b"changed")
    assert not MODULE.cache_hit(remote, destination, entry)

print("cloud transfer integrity: ok")
