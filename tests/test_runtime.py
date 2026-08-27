#!/usr/bin/env python3
"""Exercise checksum verification and atomic staging of bridge packages."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin" / "ullage-runtime.py"
SPEC = importlib.util.spec_from_file_location("ullage_runtime", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write_manifest(root: Path) -> Path:
    bridge = root / "bridge"
    artifacts = []
    for index, relative in enumerate(sorted(MODULE.REQUIRED_ARTIFACTS)):
        path = bridge / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"artifact-{index}\n".encode())
        contents = path.read_bytes()
        artifacts.append(
            {
                "path": relative,
                "size": len(contents),
                "sha256": hashlib.sha256(contents).hexdigest(),
            }
        )
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": 1,
                "runtime_id": "macos-x86_64-lsteamclient",
                "version": "test-1",
                "platform": "darwin",
                "architecture": "x86_64",
                "artifact_root": "bridge",
                "source": {"repository": "test", "commit": "test-commit"},
                "artifacts": artifacts,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


with tempfile.TemporaryDirectory(prefix="ullage-runtime-test.") as directory:
    root = Path(directory)
    manifest = write_manifest(root / "source")
    verification = MODULE.verify_manifest(manifest)
    assert verification["ready"]
    assert verification["status"] == "ready"
    assert len(verification["artifacts"]) == 4

    state = root / "state"
    package = MODULE.install_manifest(manifest, state)
    assert package["ready"]
    assert package["current"]
    assert package["runtime_id"] == "macos-x86_64-lsteamclient"
    assert package["version"] == "test-1"
    assert MODULE.current_bridge_root(state) == Path(package["bridge_root"])
    assert MODULE.verify_installed(state)["ready"]
    assert MODULE.list_installed(state)[0]["current"]

    pointer_path = state / "runtimes" / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["schema"] = 999
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    assert MODULE.current_package(state)["status"] == "invalid"
    pointer["schema"] = 1
    pointer["manifest_sha256"] = "invalid"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    assert not MODULE.current_package(state)["ready"]
    pointer["manifest_sha256"] = package["manifest_sha256"]
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    cli = ROOT / "bin" / "ullagectl"
    cli_verify = subprocess.run(
        [str(cli), "runtime", "verify", "--state-dir", str(state), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert cli_verify.returncode == 0, cli_verify.stderr
    assert json.loads(cli_verify.stdout)["package"]["ready"]
    cli_list = subprocess.run(
        [str(cli), "runtime", "list", "--state-dir", str(state), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert cli_list.returncode == 0, cli_list.stderr
    assert json.loads(cli_list.stdout)["packages"][0]["runtime_id"] == "macos-x86_64-lsteamclient"

    installed_file = Path(package["bridge_root"]) / "i386-windows/lsteamclient.dll"
    installed_file.write_bytes(b"tampered\n")
    tampered = MODULE.verify_installed(state)
    assert not tampered["ready"]
    assert any(item["status"] == "mismatch" for item in tampered["artifacts"])

    bad_manifest = root / "bad-manifest.json"
    bad_data = json.loads(manifest.read_text(encoding="utf-8"))
    bad_data["artifacts"][0]["path"] = "../outside"
    bad_manifest.write_text(json.dumps(bad_data), encoding="utf-8")
    bad_result = MODULE.verify_manifest(bad_manifest)
    assert bad_result["status"] == "invalid"
    assert not (state / "runtimes" / "bad-manifest").exists()

print("runtime package verification: ok")
