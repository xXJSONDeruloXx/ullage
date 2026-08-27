#!/usr/bin/env python3
"""Exercise the pinned Wine/GPTK host-runtime installer."""

import hashlib
import importlib.util
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("test_host_runtime_helpers", ROOT / "bin" / "ullage-host-runtime.py")
assert SPEC is not None and SPEC.loader is not None
HOST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HOST)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def archive(root: Path, output: Path, arcname: str) -> dict:
    with tarfile.open(output, "w:gz") as handle:
        handle.add(root, arcname=arcname)
    return {
        "asset": output.name,
        "url": output.as_uri(),
        "sha256": digest(output),
        "archive_size": output.stat().st_size,
        "source_url": output.as_uri(),
        "source_sha256": digest(output),
        "source_size": output.stat().st_size,
        "distribution": "test",
        "archive_root": arcname if arcname != "." else ".",
    }


with tempfile.TemporaryDirectory(prefix="ullage-host-runtime-test.") as directory:
    root = Path(directory)
    wine = root / "wine-source"
    (wine / "bin").mkdir(parents=True)
    (wine / "lib/wine").mkdir(parents=True)
    (wine / "prefix").mkdir(parents=True)
    (wine / "bin/wine").write_text("wine\n", encoding="utf-8")
    (wine / "bin/wineserver").write_text("wineserver\n", encoding="utf-8")
    (wine / "lib/wine/ntdll.so").write_text("ntdll\n", encoding="utf-8")
    (wine / "prefix/system.reg").write_text("registry\n", encoding="utf-8")
    (wine / "prefix/linked-lib").symlink_to("../lib")
    (wine / "manifest.json").write_text("{}\n", encoding="utf-8")

    gptk = root / "gptk-source"
    (gptk / "external").mkdir(parents=True)
    (gptk / "external/libd3dshared.dylib").write_text("d3d\n", encoding="utf-8")
    (gptk / "manifest.json").write_text("{}\n", encoding="utf-8")

    wine_archive = root / "wine.tar.gz"
    gptk_archive = root / "gptk.tar.gz"
    wine_component = archive(wine, wine_archive, ".")
    gptk_component = archive(gptk, gptk_archive, "gptk-test")
    release_index = root / "host-releases.json"
    release_index.write_text(
        json.dumps(
            {
                "schema": 1,
                "default": "test-host-1",
                "releases": [
                    {
                        "tag": "test-host-1",
                        "host_runtime_id": "test-host-runtime",
                        "version": "test-1",
                        "provider": "test",
                        "wine": wine_component,
                        "gptk": gptk_component,
                        "bridge_release": {"tag": "test-bridge"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    state = root / "state"
    result = HOST.fetch_release(state, releases_path=release_index)
    host = result["host"]
    assert host["ready"]
    assert host["provider"] == "test"
    assert HOST.current_host_runtime(state)["ready"]
    installed_wine = Path(host["wine_root"])
    assert (installed_wine / "prefix/linked-lib").is_symlink()
    assert (installed_wine / "prefix/linked-lib").resolve() == (installed_wine / "lib").resolve()

    cli = ROOT / "bin" / "ullagectl"
    verified = subprocess.run(
        [str(cli), "runtime", "host-verify", "--state-dir", str(state), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["host"]["ready"]

print("host runtime verification: ok")
