"""Exercise Cloud transfer integrity without contacting Steam."""

import hashlib
import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("ullage_cloud_sync", ROOT / "bin/ullage-cloud-sync.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

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

print("cloud transfer integrity: ok")
