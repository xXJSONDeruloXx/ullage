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
import tarfile
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = 1
CURRENT_FILE = "current.json"
HISTORY_FILE = "history.json"
MANIFEST_FILE = "manifest.json"
PROVENANCE_FILE = "provenance.json"
DEFAULT_ARTIFACT_ROOT = "bridge"
RELEASES_FILE = Path(__file__).resolve().parents[1] / "runtime" / "releases.json"
MAX_ARCHIVE_MEMBERS = 256
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
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


def _release_error(message: str) -> RuntimePackageError:
    return RuntimePackageError(f"runtime release: {message}")


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


def _release_index(path: str | Path | None = None) -> dict:
    index_path = _expand(path or RELEASES_FILE)
    try:
        raw = index_path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _release_error(f"release index is unreadable: {index_path}") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise _release_error(f"release index schema is not supported: {index_path}")
    default = value.get("default")
    if not isinstance(default, str) or not SAFE_NAME.fullmatch(default):
        raise _release_error("release index has an invalid default tag")
    releases = value.get("releases")
    if not isinstance(releases, list) or not releases:
        raise _release_error("release index must contain a releases list")
    normalized = []
    seen = set()
    for item in releases:
        if not isinstance(item, dict):
            raise _release_error("release index contains a malformed release")
        tag = item.get("tag")
        if not isinstance(tag, str) or not SAFE_NAME.fullmatch(tag):
            raise _release_error("release index has an invalid release tag")
        if tag in seen:
            raise _release_error(f"release index repeats tag: {tag}")
        seen.add(tag)
        runtime_id = item.get("runtime_id")
        version = item.get("version")
        repository = item.get("repository")
        asset = item.get("asset")
        url = item.get("url")
        digest = item.get("sha256")
        archive_size = item.get("archive_size")
        if not isinstance(runtime_id, str) or not SAFE_NAME.fullmatch(runtime_id):
            raise _release_error(f"release {tag} has an invalid runtime_id")
        if not isinstance(version, str) or not SAFE_NAME.fullmatch(version):
            raise _release_error(f"release {tag} has an invalid version")
        if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise _release_error(f"release {tag} has an invalid repository")
        if not isinstance(asset, str) or not SAFE_NAME.fullmatch(asset):
            raise _release_error(f"release {tag} has an invalid asset name")
        if not isinstance(url, str) or not (url.startswith("https://") or url.startswith("file://")):
            raise _release_error(f"release {tag} has an unsupported download URL")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest.lower()):
            raise _release_error(f"release {tag} has an invalid archive SHA-256")
        if not isinstance(archive_size, int) or archive_size <= 0:
            raise _release_error(f"release {tag} has an invalid archive size")
        normalized.append(
            {
                "tag": tag,
                "runtime_id": runtime_id,
                "version": version,
                "repository": repository,
                "asset": asset,
                "url": url,
                "sha256": digest.lower(),
                "archive_size": archive_size,
            }
        )
    if default not in seen:
        raise _release_error(f"default release is not listed: {default}")
    return {"schema": SCHEMA, "default": default, "releases": normalized}


def available_releases(path: str | Path | None = None) -> list[dict]:
    """Return the checked-in release lock entries."""

    return list(_release_index(path)["releases"])


def release_catalog(path: str | Path | None = None) -> dict:
    index = _release_index(path)
    return {"default": index["default"], "releases": list(index["releases"])}


def release_for_tag(tag: str | None = None, path: str | Path | None = None) -> dict:
    index = _release_index(path)
    requested = tag or index["default"]
    for release in index["releases"]:
        if release["tag"] == requested:
            return release
    available = ", ".join(item["tag"] for item in index["releases"])
    raise _release_error(f"release is not pinned: {requested}; available: {available}")


def verify_archive(path: str | Path, release: dict) -> dict:
    """Verify the locked archive before it is opened or extracted."""

    archive = _expand(path)
    result = {
        "file": str(archive),
        "expected_sha256": release["sha256"],
        "expected_size": release["archive_size"],
    }
    if archive.is_symlink() or not archive.is_file():
        result["status"] = "missing"
        result["ready"] = False
        return result
    try:
        result["actual_size"] = archive.stat().st_size
        result["actual_sha256"] = _sha256_file(archive)
    except OSError as exc:
        result["status"] = "unreadable"
        result["ready"] = False
        result["error"] = str(exc)
        return result
    result["status"] = (
        "ready"
        if result["actual_size"] == release["archive_size"]
        and result["actual_sha256"] == release["sha256"]
        else "mismatch"
    )
    result["ready"] = result["status"] == "ready"
    return result


def _download_archive(url: str, destination: Path, release: dict, headers: dict[str, str]) -> None:
    request = urllib.request.Request(url, headers=headers)
    total = 0
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as stream:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) != release["archive_size"]:
                raise _release_error(
                    f"archive size changed: expected {release['archive_size']} bytes, got {content_length}"
                )
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                total += len(chunk)
                if total > release["archive_size"]:
                    raise _release_error("downloaded archive is larger than its locked size")
                digest.update(chunk)
                stream.write(chunk)
    except RuntimePackageError:
        raise
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise _release_error(f"could not download {release['asset']}: {exc}") from exc
    actual = digest.hexdigest()
    if total != release["archive_size"] or actual != release["sha256"]:
        raise _release_error(
            f"download verification failed for {release['asset']}: "
            f"expected {release['archive_size']} bytes/{release['sha256']}, got {total} bytes/{actual}"
        )


def _archive_member_path(name: str) -> Path:
    if not name or "\\" in name:
        raise _release_error(f"archive contains an unsafe path: {name!r}")
    path = Path(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise _release_error(f"archive contains an unsafe path: {name!r}")
    return path


def _extract_archive(archive_path: Path, destination: Path) -> Path:
    try:
        archive = tarfile.open(archive_path, mode="r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise _release_error(f"archive is not a readable gzip tar: {exc}") from exc
    try:
        members = archive.getmembers()
        if not members or len(members) > MAX_ARCHIVE_MEMBERS:
            raise _release_error("archive has an invalid member count")
        root_name = None
        seen = set()
        unpacked = 0
        parsed = []
        for member in members:
            relative = _archive_member_path(member.name)
            if len(relative.parts) < 2:
                if not member.isdir() or len(relative.parts) != 1:
                    raise _release_error("archive must contain one package directory")
            if root_name is None:
                root_name = relative.parts[0]
                if not SAFE_NAME.fullmatch(root_name):
                    raise _release_error(f"archive has an invalid package directory: {root_name}")
            elif relative.parts[0] != root_name:
                raise _release_error("archive contains more than one package directory")
            key = relative.as_posix()
            if key in seen:
                raise _release_error(f"archive repeats a path: {key}")
            seen.add(key)
            if member.issym() or member.islnk() or member.isdev() or not (member.isdir() or member.isfile()):
                raise _release_error(f"archive contains an unsupported member: {key}")
            if member.size < 0:
                raise _release_error(f"archive has a negative member size: {key}")
            unpacked += member.size
            if unpacked > MAX_ARCHIVE_BYTES:
                raise _release_error("archive expands beyond the safety limit")
            parsed.append((member, relative))
        if root_name is None:
            raise _release_error("archive has no package directory")
        destination.mkdir(parents=True, exist_ok=True)
        for member, relative in parsed:
            target = destination / relative
            if not _within(destination, target):
                raise _release_error(f"archive escapes its staging directory: {relative}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise _release_error(f"archive extraction collides with an existing path: {relative}")
            source = archive.extractfile(member)
            if source is None:
                raise _release_error(f"archive member cannot be read: {relative}")
            with source, target.open("xb") as stream:
                shutil.copyfileobj(source, stream, length=1024 * 1024)
            target.chmod(member.mode & 0o777)
        manifest = destination / root_name / MANIFEST_FILE
        if not manifest.is_file():
            raise _release_error("archive does not contain a package manifest")
        verification = verify_manifest(manifest)
        if not verification.get("ready"):
            raise _release_error(
                "extracted package failed manifest verification: "
                + (verification.get("error") or "one or more artifacts are incomplete")
            )
        return manifest
    except tarfile.TarError as exc:
        raise _release_error(f"archive could not be read: {exc}") from exc
    finally:
        archive.close()


def fetch_release(
    state_root: str | Path,
    tag: str | None = None,
    cache_dir: str | Path | None = None,
    releases_path: str | Path | None = None,
) -> dict:
    """Fetch, verify, extract, and atomically install a locked release."""

    release = release_for_tag(tag, releases_path)
    root = _expand(state_root)
    cache = _expand(cache_dir) if cache_dir else root / "downloads"
    if cache.is_symlink():
        raise _release_error(f"download cache is a symlink: {cache}")
    cache.mkdir(parents=True, exist_ok=True)
    archive_path = cache / release["asset"]
    if archive_path.is_symlink():
        raise _release_error(f"downloaded archive is a symlink: {archive_path}")
    cached = verify_archive(archive_path, release)
    if not cached.get("ready"):
        temporary = cache / f".{release['asset']}.{os.getpid()}.part"
        try:
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()
            _download_archive(
                release["url"],
                temporary,
                release,
                {"User-Agent": "ullage-runtime/1"},
            )
            os.replace(temporary, archive_path)
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass
    archive = verify_archive(archive_path, release)
    if not archive.get("ready"):
        raise _release_error("cached archive failed verification")
    extraction = Path(tempfile.mkdtemp(prefix=".ullage-release-", dir=cache))
    try:
        manifest = _extract_archive(archive_path, extraction)
        package = install_manifest(manifest, root)
    finally:
        shutil.rmtree(extraction, ignore_errors=True)
    return {"release": release, "archive": archive, "package": package}


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


def _pointer_for(package: dict) -> dict:
    return {
        "schema": SCHEMA,
        "runtime_id": package["runtime_id"],
        "version": package["version"],
        "manifest_sha256": package["manifest_sha256"],
    }


def _valid_pointer(value: object) -> dict | None:
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        return None
    try:
        runtime_id = _safe_name(value.get("runtime_id"), "current runtime_id")
        version = _safe_name(value.get("version"), "current version")
    except RuntimePackageError:
        return None
    digest = value.get("manifest_sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        return None
    return {
        "schema": SCHEMA,
        "runtime_id": runtime_id,
        "version": version,
        "manifest_sha256": digest,
    }


def _same_pointer(left: object, right: object) -> bool:
    return _valid_pointer(left) == _valid_pointer(right)


def _history_entries(state_root: str | Path) -> list[dict]:
    value = _read_json(_expand(state_root) / "runtimes" / HISTORY_FILE)
    if value.get("schema") != SCHEMA or not isinstance(value.get("entries"), list):
        return []
    return [pointer for item in value["entries"] if (pointer := _valid_pointer(item))]


def _activate_package(state_root: Path, package: dict) -> None:
    """Atomically make a verified package current and retain rollback history."""

    pointer_path = state_root / "runtimes" / CURRENT_FILE
    new_pointer = _pointer_for(package)
    old_pointer = _read_json(pointer_path)
    if not _same_pointer(old_pointer, new_pointer):
        old_pointer = _valid_pointer(old_pointer)
        if old_pointer:
            entries = [old_pointer]
            entries.extend(
                pointer
                for pointer in _history_entries(state_root)
                if not _same_pointer(pointer, old_pointer)
            )
            _write_json(
                state_root / "runtimes" / HISTORY_FILE,
                {"schema": SCHEMA, "entries": entries[:16]},
            )
    _write_json(pointer_path, new_pointer)


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
            _activate_package(root, existing)
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

    installed = _installed_package(package_root, current=True)
    _activate_package(root, installed)
    return installed


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


def rollback(
    state_root: str | Path,
    runtime_id: str | None = None,
    version: str | None = None,
) -> dict:
    """Switch to a verified previous package without deleting the current one."""

    if (runtime_id is None) != (version is None):
        raise RuntimePackageError("runtime rollback requires both --runtime-id and --version")
    root = _expand(state_root)
    current = current_package(root)
    if not current or not current.get("ready"):
        raise RuntimePackageError("cannot roll back without a verified active runtime package")
    target = None
    if runtime_id is not None and version is not None:
        candidate = verify_installed(root, runtime_id, version)
        if not candidate.get("ready"):
            raise RuntimePackageError(
                f"rollback target is not ready: {candidate.get('error') or candidate.get('root')}"
            )
        target = candidate
    else:
        for pointer in _history_entries(root):
            if _same_pointer(pointer, current):
                continue
            candidate = verify_installed(root, pointer["runtime_id"], pointer["version"])
            if candidate.get("ready") and candidate.get("manifest_sha256") == pointer["manifest_sha256"]:
                target = candidate
                break
        if target is None:
            raise RuntimePackageError("no verified runtime rollback target is available")
    _activate_package(root, target)
    target["current"] = True
    target["rolled_back_from"] = {
        "runtime_id": current.get("runtime_id"),
        "version": current.get("version"),
        "manifest_sha256": current.get("manifest_sha256"),
    }
    return target


FORWARDER_RELATIVE_PATH = Path("drive_c/Program Files (x86)/Steam/steamclient64.dll")


def stage_forwarder(state_root: str | Path, prefix: str | Path) -> dict:
    """Atomically stage the active package's x64 forwarder in a Wine prefix."""

    root = _expand(state_root)
    package = current_package(root)
    if not package or not package.get("ready"):
        raise RuntimePackageError("cannot stage the forwarder without a verified active runtime package")
    source = Path(package["bridge_root"]) / "x86_64-windows/steamclient64.dll"
    if source.is_symlink() or not source.is_file():
        raise RuntimePackageError(f"active runtime forwarder is missing: {source}")
    prefix_root = _expand(prefix)
    if prefix_root.is_symlink() or not prefix_root.is_dir() or not (prefix_root / "system.reg").is_file():
        raise RuntimePackageError(f"Wine prefix is missing or not initialized: {prefix_root}")
    target = prefix_root / FORWARDER_RELATIVE_PATH
    parent = target.parent
    if parent.is_symlink():
        raise RuntimePackageError(f"Wine prefix Steam directory is a symlink: {parent}")
    parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_name(target.name + ".ullage-original")
    if target.is_file() and not target.is_symlink() and _sha256_file(target) == _sha256_file(source):
        return {
            "status": "ready",
            "changed": False,
            "source": str(source),
            "target": str(target),
            "original_backup": str(backup) if backup.exists() else None,
            "package": package,
        }
    if backup.exists() or backup.is_symlink():
        if target.is_symlink():
            raise RuntimePackageError(
                f"forwarder target changed outside Ullage and its original backup exists: {target}"
            )
    temporary = parent / f".{target.name}.{os.getpid()}.tmp"
    moved_original = False
    try:
        if target.exists() or target.is_symlink():
            if not backup.exists() and not backup.is_symlink():
                os.replace(target, backup)
                moved_original = True
        shutil.copyfile(source, temporary)
        shutil.copystat(source, temporary)
        os.replace(temporary, target)
    except (OSError, RuntimePackageError) as exc:
        try:
            temporary.unlink()
        except OSError:
            pass
        if moved_original and not target.exists() and not target.is_symlink() and backup.exists():
            os.replace(backup, target)
        raise RuntimePackageError(f"could not stage x64 Steam client forwarder: {exc}") from exc
    return {
        "status": "ready",
        "changed": True,
        "source": str(source),
        "target": str(target),
        "original_backup": str(backup) if backup.exists() else None,
        "package": package,
    }


def restore_forwarder(prefix: str | Path) -> dict:
    """Restore the prefix file saved by :func:`stage_forwarder`."""

    prefix_root = _expand(prefix)
    target = prefix_root / FORWARDER_RELATIVE_PATH
    backup = target.with_name(target.name + ".ullage-original")
    if not backup.exists() and not backup.is_symlink():
        raise RuntimePackageError(f"no Ullage forwarder backup exists for prefix: {prefix_root}")
    temporary = target.with_name(f".{target.name}.{os.getpid()}.restore")
    try:
        if target.exists() or target.is_symlink():
            os.replace(target, temporary)
        os.replace(backup, target)
    except OSError as exc:
        if temporary.exists() and not target.exists() and not target.is_symlink():
            os.replace(temporary, target)
        raise RuntimePackageError(f"could not restore x64 Steam client forwarder: {exc}") from exc
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass
    return {"status": "restored", "target": str(target), "original_backup": str(backup)}
