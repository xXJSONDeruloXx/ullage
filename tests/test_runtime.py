#!/usr/bin/env python3
"""Exercise checksum verification and atomic staging of bridge packages."""

import hashlib
import importlib.util
import json
import os
import subprocess
import tarfile
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin" / "ullage-runtime.py"
SPEC = importlib.util.spec_from_file_location("ullage_runtime", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write_manifest(root: Path, version: str = "test-1") -> Path:
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
                "version": version,
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


def write_release(source: Path, release_root: Path, version: str) -> tuple[Path, Path]:
    manifest = write_manifest(source, version)
    package_root = release_root / f"package-{version}"
    package_root.mkdir(parents=True)
    (package_root / "bridge").mkdir()
    for artifact in MODULE.REQUIRED_ARTIFACTS:
        destination = package_root / "bridge" / artifact
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((source / "bridge" / artifact).read_bytes())
    (package_root / "manifest.json").write_bytes(manifest.read_bytes())
    archive = release_root / f"runtime-{version}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(package_root, arcname=package_root.name)
    return archive, package_root / "manifest.json"


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
    installed_file.write_bytes((root / "source/bridge/i386-windows/lsteamclient.dll").read_bytes())

    bad_manifest = root / "bad-manifest.json"
    bad_data = json.loads(manifest.read_text(encoding="utf-8"))
    bad_data["artifacts"][0]["path"] = "../outside"
    bad_manifest.write_text(json.dumps(bad_data), encoding="utf-8")
    bad_result = MODULE.verify_manifest(bad_manifest)
    assert bad_result["status"] == "invalid"
    assert not (state / "runtimes" / "bad-manifest").exists()

    releases = root / "releases"
    releases.mkdir()
    archive, _ = write_release(root / "source-v2", releases, "test-2")
    archive_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    release_index = root / "releases.json"
    release_index.write_text(
        json.dumps(
            {
                "schema": 1,
                "default": "test-release-2",
                "releases": [
                    {
                        "tag": "test-release-2",
                        "runtime_id": "macos-x86_64-lsteamclient",
                        "version": "test-2",
                        "repository": "test/example",
                        "asset": archive.name,
                        "url": archive.as_uri(),
                        "sha256": archive_digest,
                        "archive_size": archive.stat().st_size,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    fetched = MODULE.fetch_release(state, releases_path=release_index)
    assert fetched["archive"]["ready"]
    assert fetched["package"]["version"] == "test-2"
    assert MODULE.current_package(state)["version"] == "test-2"

    rolled_back = MODULE.rollback(state)
    assert rolled_back["version"] == "test-1"
    assert MODULE.current_package(state)["version"] == "test-1"

    cli_fetch = subprocess.run(
        [
            str(cli),
            "runtime", "fetch",
            "--state-dir", str(state),
            "--release-index", str(release_index),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert cli_fetch.returncode == 0, cli_fetch.stderr
    assert json.loads(cli_fetch.stdout)["package"]["version"] == "test-2"
    cli_rollback = subprocess.run(
        [str(cli), "runtime", "rollback", "--state-dir", str(state), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert cli_rollback.returncode == 0, cli_rollback.stderr
    assert json.loads(cli_rollback.stdout)["package"]["version"] == "test-1"

    prefix = root / "prefix"
    target = prefix / MODULE.FORWARDER_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    (prefix / "system.reg").touch()
    original = prefix / "original-steamclient64.dll"
    original.write_bytes(b"original\n")
    target.symlink_to(original)
    staged = MODULE.stage_forwarder(state, prefix)
    assert staged["changed"]
    assert target.is_file() and not target.is_symlink()
    assert target.read_bytes() == (Path(rolled_back["bridge_root"]) / "x86_64-windows/steamclient64.dll").read_bytes()
    assert target.with_name(target.name + ".ullage-original").is_symlink()
    restored = MODULE.restore_forwarder(prefix)
    assert restored["status"] == "restored"
    assert target.is_symlink()
    assert target.resolve() == original.resolve()

print("runtime package verification: ok")
