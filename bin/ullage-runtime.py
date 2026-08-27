#!/usr/bin/env python3
"""Install and verify versioned Ullage bridge runtime packages.

Runtime packages contain only the small lsteamclient bridge artifacts. Wine,
GPTK/D3DMetal, native Steam, and the Wine prefix remain host-provided inputs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = 1
CURRENT_FILE = "current.json"
MANIFEST_FILE = "manifest.json"
PROVENANCE_FILE = "provenance.json"
DEFAULT_ARTIFACT_ROOT = "bridge"
REQUIRED_ARTIFACTS = {
    "x86_64-unix/lsteamclient.so",
    "i386-windows/lsteamclient.dll",
    "x86_64-windows/lsteamclient.dll",
    "x86_64-windows/steamclient64.dll",
}
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RuntimePackageError(ValueError):
    """A user-facing runtime package error."""


def _expand(path: str | Path) -> Path:
    return Path(path).expanduser()


def _sha256_bytes(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: object, label: str) -> str:
    if not isinstance(value, str) or not SAFE_NAME.fullmatch(value):
        raise RuntimePackageError(f"runtime manifest has an invalid {label}")
    return value


def _safe_relative_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise RuntimePackageError(f"runtime manifest has an invalid {label}")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimePackageError(f"runtime manifest has an unsafe {label}: {value}")
    return path


def _within(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _manifest_data(path: Path) -> tuple[dict, bytes, dict[str, dict]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RuntimePackageError(f"runtime manifest is unreadable: {path}: {exc}") from exc
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimePackageError(f"runtime manifest is not valid JSON: {path}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise RuntimePackageError(f"runtime manifest schema is not supported: {path}")
    _safe_name(manifest.get("runtime_id"), "runtime_id")
    _safe_name(manifest.get("version"), "version")
    artifact_root = manifest.get("artifact_root", DEFAULT_ARTIFACT_ROOT)
    _safe_relative_path(artifact_root, "artifact_root")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise RuntimePackageError("runtime manifest must contain an artifacts list")

    specs: dict[str, dict] = {}
    for item in artifacts:
        if not isinstance(item, dict):
            raise RuntimePackageError("runtime manifest contains a malformed artifact")
        relative = _safe_relative_path(item.get("path"), "artifact path")
        key = relative.as_posix()
        if key in specs:
            raise RuntimePackageError(f"runtime manifest repeats artifact: {key}")
        digest = item.get("sha256")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest.lower()):
            raise RuntimePackageError(f"runtime manifest has an invalid SHA-256 for {key}")
        size = item.get("size")
        if not isinstance(size, int) or size < 0:
            raise RuntimePackageError(f"runtime manifest has an invalid size for {key}")
        specs[key] = {
            "path": key,
            "sha256": digest.lower(),
            "size": size,
            "kind": str(item.get("kind") or "bridge"),
        }
    missing = sorted(REQUIRED_ARTIFACTS - specs.keys())
    if missing:
        raise RuntimePackageError(
            "runtime manifest is missing required artifacts: " + ", ".join(missing)
        )
    return manifest, raw, specs


def _artifact_root(manifest_path: Path, manifest: dict, source_root: str | Path | None) -> Path:
    if source_root is not None:
        return _expand(source_root)
    return manifest_path.parent / str(manifest.get("artifact_root", DEFAULT_ARTIFACT_ROOT))


def load_manifest(path: str | Path) -> dict:
    """Load and validate a package manifest without checking its artifacts."""

    manifest, raw, specs = _manifest_data(_expand(path))
    return {
        "manifest": manifest,
        "manifest_sha256": _sha256_bytes(raw),
        "artifacts": list(specs.values()),
    }


def verify_manifest(path: str | Path, source_root: str | Path | None = None) -> dict:
    """Verify every manifest artifact and return actionable per-file results."""

    manifest_path = _expand(path)
    try:
        manifest, raw, specs = _manifest_data(manifest_path)
    except RuntimePackageError as exc:
        return {
            "status": "invalid",
            "ready": False,
            "manifest": str(manifest_path),
            "error": str(exc),
        }

    root = _artifact_root(manifest_path, manifest, source_root)
    root_resolved = root.resolve(strict=False)
    artifacts = []
    for spec in specs.values():
        relative = Path(spec["path"])
        artifact = root / relative
        record = {
            "path": spec["path"],
            "file": str(artifact),
            "expected_sha256": spec["sha256"],
            "expected_size": spec["size"],
            "kind": spec["kind"],
        }
        if not _within(root_resolved, artifact):
            record["status"] = "unsafe_path"
        elif artifact.is_symlink() or not artifact.is_file():
            record["status"] = "missing"
        else:
            try:
                record["actual_size"] = artifact.stat().st_size
                record["actual_sha256"] = _sha256_file(artifact)
            except OSError as exc:
                record["status"] = "unreadable"
                record["error"] = str(exc)
            else:
                record["status"] = (
                    "ready"
                    if record["actual_size"] == spec["size"]
                    and record["actual_sha256"] == spec["sha256"]
                    else "mismatch"
                )
        artifacts.append(record)

    return {
        "schema": SCHEMA,
        "runtime_id": manifest["runtime_id"],
        "version": manifest["version"],
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256_bytes(raw),
        "source_root": str(root),
        "artifacts": artifacts,
        "status": "ready" if all(item["status"] == "ready" for item in artifacts) else "incomplete",
        "ready": all(item["status"] == "ready" for item in artifacts),
    }


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _package_path(state_root: Path, runtime_id: str, version: str) -> Path:
    _safe_name(runtime_id, "runtime_id")
    _safe_name(version, "version")
    return state_root / "runtimes" / runtime_id / version


def _installed_package(package_root: Path, current: bool = False) -> dict:
    manifest_path = package_root / MANIFEST_FILE
    result = verify_manifest(manifest_path, package_root / DEFAULT_ARTIFACT_ROOT)
    result.update(
        {
            "root": str(package_root),
            "bridge_root": str(package_root / DEFAULT_ARTIFACT_ROOT),
            "provenance": str(package_root / PROVENANCE_FILE),
            "current": current,
        }
    )
    if (package_root / DEFAULT_ARTIFACT_ROOT).is_symlink():
        result["status"] = "incomplete"
        result["ready"] = False
        result["error"] = "installed runtime bridge directory is a symlink"
    provenance = _read_json(package_root / PROVENANCE_FILE)
    result["provenance_data"] = provenance or None
    if result.get("ready"):
        if not provenance:
            result["status"] = "incomplete"
            result["ready"] = False
            result["error"] = "installed runtime provenance is missing"
        elif provenance.get("schema") != SCHEMA:
            result["status"] = "incomplete"
            result["ready"] = False
            result["error"] = "installed runtime provenance schema is not supported"
        elif any(
            provenance.get(field) != result.get(field)
            for field in ("runtime_id", "version", "manifest_sha256")
        ):
            result["status"] = "incomplete"
            result["ready"] = False
            result["error"] = "installed runtime provenance does not match its manifest"
    return result


def current_package(state_root: str | Path) -> dict | None:
    """Return the active package status, including an invalid pointer."""

    root = _expand(state_root)
    pointer = _read_json(root / "runtimes" / CURRENT_FILE)
    if not pointer:
        return None
    if pointer.get("schema") != SCHEMA:
        return {
            "status": "invalid",
            "ready": False,
            "current": True,
            "error": "active runtime pointer schema is not supported",
            "pointer": str(root / "runtimes" / CURRENT_FILE),
        }
    try:
        runtime_id = _safe_name(pointer.get("runtime_id"), "current runtime_id")
        version = _safe_name(pointer.get("version"), "current version")
        package_root = _package_path(root, runtime_id, version)
    except RuntimePackageError as exc:
        return {
            "status": "invalid",
            "ready": False,
            "current": True,
            "error": str(exc),
            "pointer": str(root / "runtimes" / CURRENT_FILE),
        }
    if not package_root.is_dir() or package_root.is_symlink():
        return {
            "status": "missing",
            "ready": False,
            "current": True,
            "runtime_id": runtime_id,
            "version": version,
            "root": str(package_root),
            "bridge_root": str(package_root / DEFAULT_ARTIFACT_ROOT),
            "error": "active runtime package directory is missing",
        }
    result = _installed_package(package_root, current=True)
    expected_manifest = pointer.get("manifest_sha256")
    if not isinstance(expected_manifest, str) or not SHA256.fullmatch(expected_manifest):
        result["status"] = "incomplete"
        result["ready"] = False
        result["error"] = "active runtime pointer has an invalid manifest digest"
    elif expected_manifest != result.get("manifest_sha256"):
        result["status"] = "incomplete"
        result["ready"] = False
        result["error"] = "active runtime pointer does not match its manifest"
    return result


def current_bridge_root(state_root: str | Path) -> Path | None:
    package = current_package(state_root)
    if not package or not package.get("bridge_root"):
        return None
    # An active but invalid package must remain visible to doctor/install so it
    # cannot be silently replaced by an unrelated manually assembled bridge.
    return Path(package["bridge_root"])


def list_installed(state_root: str | Path) -> list[dict]:
    root = _expand(state_root) / "runtimes"
    current = current_package(state_root)
    current_key = (
        current.get("runtime_id"), current.get("version")
    ) if current else (None, None)
    packages = []
    try:
        runtime_dirs = sorted(root.iterdir())
    except OSError:
        return packages
    for runtime_dir in runtime_dirs:
        if not runtime_dir.is_dir() or runtime_dir.is_symlink() or runtime_dir.name.startswith("."):
            continue
        try:
            versions = sorted(runtime_dir.iterdir())
        except OSError:
            continue
        for version_dir in versions:
            if not version_dir.is_dir() or version_dir.is_symlink() or version_dir.name.startswith("."):
                continue
            if not (version_dir / MANIFEST_FILE).is_file():
                continue
            item = _installed_package(
                version_dir,
                current=(runtime_dir.name, version_dir.name) == current_key,
            )
            packages.append(item)
    return packages


def package_for_bridge_root(bridge_root: str | Path, state_root: str | Path) -> dict | None:
    candidate = _expand(bridge_root).resolve(strict=False)
    for package in list_installed(state_root):
        if Path(package.get("bridge_root", "")).resolve(strict=False) == candidate:
            return package
    return None


def install_manifest(
    manifest_path: str | Path,
    state_root: str | Path,
    source_root: str | Path | None = None,
) -> dict:
    """Verify and atomically stage a package under ``state_root/runtimes``."""

    manifest_file = _expand(manifest_path)
    try:
        manifest, raw, specs = _manifest_data(manifest_file)
    except RuntimePackageError:
        raise
    verification = verify_manifest(manifest_file, source_root)
    if not verification.get("ready"):
        details = verification.get("error") or ", ".join(
            f"{item['path']}: {item['status']}"
            for item in verification.get("artifacts", [])
            if item.get("status") != "ready"
        )
        raise RuntimePackageError(f"runtime package verification failed: {details}")

    root = _expand(state_root)
    runtime_id = manifest["runtime_id"]
    version = manifest["version"]
    package_root = _package_path(root, runtime_id, version)
    package_root.parent.mkdir(parents=True, exist_ok=True)
    if package_root.is_symlink():
        raise RuntimePackageError(f"runtime package path is a symlink: {package_root}")
    if package_root.exists():
        existing = _installed_package(package_root)
        if existing.get("ready") and existing.get("manifest_sha256") == verification.get("manifest_sha256"):
            _write_json(
                root / "runtimes" / CURRENT_FILE,
                {
                    "schema": SCHEMA,
                    "runtime_id": runtime_id,
                    "version": version,
                    "manifest_sha256": verification["manifest_sha256"],
                },
            )
            existing["current"] = True
            return existing
        raise RuntimePackageError(
            f"runtime package already exists with different or invalid contents: {package_root}"
        )

    artifact_root = Path(verification["source_root"])
    temporary = Path(tempfile.mkdtemp(prefix=f".{version}-staging-", dir=package_root.parent))
    try:
        for spec in specs.values():
            source = artifact_root / spec["path"]
            destination = temporary / DEFAULT_ARTIFACT_ROOT / spec["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            shutil.copystat(source, destination)
        shutil.copyfile(manifest_file, temporary / MANIFEST_FILE)
        provenance = {
            "schema": SCHEMA,
            "runtime_id": runtime_id,
            "version": version,
            "manifest": MANIFEST_FILE,
            "manifest_sha256": verification["manifest_sha256"],
            "installed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "source": manifest.get("source", {}),
        }
        _write_json(temporary / PROVENANCE_FILE, provenance)
        staged = verify_manifest(temporary / MANIFEST_FILE, temporary / DEFAULT_ARTIFACT_ROOT)
        if not staged.get("ready"):
            raise RuntimePackageError("staged runtime package failed its post-copy verification")
        os.replace(temporary, package_root)
    except (OSError, RuntimePackageError):
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    _write_json(
        root / "runtimes" / CURRENT_FILE,
        {
            "schema": SCHEMA,
            "runtime_id": runtime_id,
            "version": version,
            "manifest_sha256": verification["manifest_sha256"],
        },
    )
    return _installed_package(package_root, current=True)


def verify_installed(
    state_root: str | Path,
    runtime_id: str | None = None,
    version: str | None = None,
) -> dict:
    if runtime_id is None and version is None:
        package = current_package(state_root)
        if package is None:
            return {
                "status": "missing",
                "ready": False,
                "error": "no active runtime package is installed",
            }
        return package
    if runtime_id is None or version is None:
        return {
            "status": "invalid",
            "ready": False,
            "error": "runtime verify requires both --runtime-id and --version",
        }
    try:
        package_root = _package_path(_expand(state_root), runtime_id, version)
    except RuntimePackageError as exc:
        return {"status": "invalid", "ready": False, "error": str(exc)}
    if not package_root.is_dir() or package_root.is_symlink():
        return {
            "status": "missing",
            "ready": False,
            "runtime_id": runtime_id,
            "version": version,
            "root": str(package_root),
            "error": "runtime package directory is missing",
        }
    current = current_package(state_root)
    return _installed_package(
        package_root,
        current=bool(current and current.get("runtime_id") == runtime_id and current.get("version") == version),
    )
