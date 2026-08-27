#!/usr/bin/env python3
"""Install and verify a pinned host Wine/GPTK runtime for Ullage.

The host runtime is intentionally separate from the small lsteamclient bridge
package.  The GameHub Wine archive is released byte-for-byte with its recorded
source hash; GPTK is fetched from its original source or supplied locally and
is never silently represented as an Ullage-owned binary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = 1
CURRENT_FILE = "current.json"
HISTORY_FILE = "history.json"
MANIFEST_FILE = "host-manifest.json"
HOST_RELEASES_FILE = Path(__file__).resolve().parents[1] / "runtime" / "host-releases.json"
HOST_ROOT_NAME = "host-runtimes"
MAX_ARCHIVE_MEMBERS = 20_000
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class HostRuntimeError(ValueError):
    """A user-facing host-runtime error."""


def _host_error(message: str) -> HostRuntimeError:
    return HostRuntimeError(f"host runtime: {message}")


def _expand(path: str | Path) -> Path:
    return Path(path).expanduser()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: object, label: str) -> str:
    if not isinstance(value, str) or not SAFE_NAME.fullmatch(value):
        raise HostRuntimeError(f"host runtime metadata has an invalid {label}")
    return value


def _safe_relative(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise HostRuntimeError(f"host runtime metadata has an invalid {label}")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HostRuntimeError(f"host runtime metadata has an unsafe {label}: {value}")
    return path


def _within(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


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


def _source_url(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith(("https://", "file://")):
        raise _host_error(f"{label} must use HTTPS")
    return value


def _component(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise _host_error(f"release is missing the {label} component")
    asset = _safe_name(value.get("asset"), f"{label}.asset")
    url = _source_url(value.get("url"), f"{label}.url")
    digest = value.get("sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest.lower()):
        raise _host_error(f"{label} has an invalid SHA-256")
    size = value.get("archive_size")
    if not isinstance(size, int) or size <= 0:
        raise _host_error(f"{label} has an invalid archive size")
    source_url = _source_url(value.get("source_url"), f"{label}.source_url")
    source_digest = value.get("source_sha256")
    if not isinstance(source_digest, str) or not SHA256.fullmatch(source_digest.lower()):
        raise _host_error(f"{label} has an invalid source SHA-256")
    source_size = value.get("source_size")
    if not isinstance(source_size, int) or source_size <= 0:
        raise _host_error(f"{label} has an invalid source archive size")
    if source_digest.lower() != digest.lower() or source_size != size:
        raise _host_error(f"{label} release and source hashes/sizes must match")
    return {
        "asset": asset,
        "url": url,
        "sha256": digest.lower(),
        "archive_size": size,
        "source_url": source_url,
        "source_sha256": source_digest.lower(),
        "source_size": source_size,
        "distribution": str(value.get("distribution") or "unknown"),
        "archive_root": str(value.get("archive_root") or "."),
    }


def _release_index(path: str | Path | None = None) -> dict:
    index_path = _expand(path or HOST_RELEASES_FILE)
    try:
        value = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _host_error(f"release index is unreadable: {index_path}") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise _host_error(f"release index schema is not supported: {index_path}")
    default = _safe_name(value.get("default"), "default release tag")
    releases = value.get("releases")
    if not isinstance(releases, list) or not releases:
        raise _host_error("release index must contain a releases list")
    normalized = []
    seen = set()
    for item in releases:
        if not isinstance(item, dict):
            raise _host_error("release index contains a malformed release")
        tag = _safe_name(item.get("tag"), "release tag")
        if tag in seen:
            raise _host_error(f"release index repeats tag: {tag}")
        seen.add(tag)
        host_id = _safe_name(item.get("host_runtime_id"), f"release {tag}.host_runtime_id")
        version = _safe_name(item.get("version"), f"release {tag}.version")
        provider = _safe_name(item.get("provider"), f"release {tag}.provider")
        wine = _component(item.get("wine"), f"release {tag}.wine")
        gptk = _component(item.get("gptk"), f"release {tag}.gptk")
        if wine["archive_root"] != ".":
            raise _host_error(f"release {tag} Wine archive root must be '.'")
        if not SAFE_NAME.fullmatch(gptk["archive_root"]):
            raise _host_error(f"release {tag} GPTK archive root is unsafe")
        normalized.append(
            {
                "tag": tag,
                "host_runtime_id": host_id,
                "version": version,
                "provider": provider,
                "wine": wine,
                "gptk": gptk,
                "wine_manifest": item.get("wine_manifest", {}),
                "bridge_release": item.get("bridge_release", {}),
                "notes": str(item.get("notes") or ""),
            }
        )
    if default not in seen:
        raise _host_error(f"default release is not listed: {default}")
    return {"schema": SCHEMA, "default": default, "releases": normalized}


def available_releases(path: str | Path | None = None) -> list[dict]:
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
    raise _host_error(f"release is not pinned: {requested}; available: {available}")


def verify_archive(path: str | Path, component: dict) -> dict:
    archive = _expand(path)
    result = {
        "file": str(archive),
        "expected_sha256": component["sha256"],
        "expected_size": component["archive_size"],
    }
    if archive.is_symlink() or not archive.is_file():
        result.update(status="missing", ready=False)
        return result
    try:
        result["actual_size"] = archive.stat().st_size
        result["actual_sha256"] = _sha256_file(archive)
    except OSError as exc:
        result.update(status="unreadable", ready=False, error=str(exc))
        return result
    result["status"] = (
        "ready"
        if result["actual_size"] == component["archive_size"]
        and result["actual_sha256"] == component["sha256"]
        else "mismatch"
    )
    result["ready"] = result["status"] == "ready"
    return result


def _download_archive(url: str, destination: Path, component: dict) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "ullage-host-runtime/1"})
    total = 0
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=180) as response, destination.open("wb") as stream:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) != component["archive_size"]:
                raise _host_error(
                    f"archive size changed: expected {component['archive_size']} bytes, got {content_length}"
                )
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                total += len(chunk)
                if total > component["archive_size"]:
                    raise _host_error("downloaded archive is larger than its locked size")
                digest.update(chunk)
                stream.write(chunk)
    except HostRuntimeError:
        raise
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise _host_error(f"could not download {component['asset']}: {exc}") from exc
    actual = digest.hexdigest()
    if total != component["archive_size"] or actual != component["sha256"]:
        raise _host_error(
            f"download verification failed for {component['asset']}: "
            f"expected {component['archive_size']} bytes/{component['sha256']}, "
            f"got {total} bytes/{actual}"
        )


def _ensure_cached(component: dict, cache: Path, local: str | Path | None = None) -> tuple[Path, dict]:
    if local is not None:
        archive = _expand(local)
        verification = verify_archive(archive, component)
        if not verification.get("ready"):
            raise _host_error(
                f"local {component['asset']} failed verification: "
                f"{verification.get('status')} ({verification.get('actual_sha256', 'unavailable')})"
            )
        return archive, verification
    if cache.is_symlink():
        raise _host_error(f"download cache is a symlink: {cache}")
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / component["asset"]
    if archive.is_symlink():
        raise _host_error(f"downloaded archive is a symlink: {archive}")
    cached = verify_archive(archive, component)
    if not cached.get("ready"):
        temporary = cache / f".{component['asset']}.{os.getpid()}.part"
        try:
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()
            _download_archive(component["url"], temporary, component)
            os.replace(temporary, archive)
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass
    verification = verify_archive(archive, component)
    if not verification.get("ready"):
        raise _host_error(f"cached archive failed verification: {archive}")
    return archive, verification


def _tar_path() -> str:
    return shutil.which("tar") or "/usr/bin/tar"


def _archive_names(archive: Path, component: dict) -> list[str]:
    try:
        result = subprocess.run(
            [_tar_path(), "-tf", str(archive)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise _host_error(f"could not execute tar: {exc}") from exc
    if result.returncode != 0:
        raise _host_error(f"archive cannot be listed: {(result.stderr or result.stdout).strip()}")
    names = []
    expected_root = component["archive_root"]
    for raw_name in result.stdout.splitlines():
        name = raw_name.strip().rstrip("/")
        if not name or name in {".", "./"}:
            continue
        if "\\" in name:
            raise _host_error(f"archive contains an unsafe path: {raw_name!r}")
        path = Path(name)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise _host_error(f"archive contains an unsafe path: {raw_name!r}")
        if expected_root == ".":
            normalized = path.as_posix()
        else:
            if not path.parts or path.parts[0] != expected_root:
                raise _host_error(f"archive contains an unexpected root: {raw_name!r}")
            normalized = path.as_posix()
        names.append(normalized)
    if not names or len(names) > MAX_ARCHIVE_MEMBERS:
        raise _host_error("archive has an invalid member count")
    return names


def _validate_tree(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise _host_error(f"extracted runtime root is not a directory: {root}")
    resolved_root = root.resolve(strict=False)
    total = 0
    count = 0
    for current, directories, files in os.walk(root, followlinks=False):
        entries = [Path(current) / name for name in directories + files]
        for entry in entries:
            count += 1
            if count > MAX_ARCHIVE_MEMBERS:
                raise _host_error("extracted runtime has too many members")
            if entry.is_symlink():
                try:
                    target = (entry.parent / os.readlink(entry)).resolve(strict=False)
                except OSError as exc:
                    raise _host_error(f"cannot inspect extracted symlink: {entry}") from exc
                if not _within(resolved_root, target):
                    raise _host_error(f"extracted symlink escapes its runtime root: {entry}")
                continue
            if not entry.is_dir() and not entry.is_file():
                raise _host_error(f"extracted runtime contains an unsupported entry: {entry}")
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError as exc:
                    raise _host_error(f"cannot inspect extracted runtime file: {entry}") from exc
                if total > MAX_ARCHIVE_BYTES:
                    raise _host_error("extracted runtime exceeds the safety size limit")


def _extract_component(archive: Path, component: dict, destination: Path) -> None:
    names = _archive_names(archive, component)
    expected_root = component["archive_root"]
    required = (
        ("manifest.json", "bin/wine", "bin/wineserver", "lib", "prefix")
        if expected_root == "."
        else (f"{expected_root}/manifest.json", f"{expected_root}/external/libd3dshared.dylib")
    )
    if any(item not in names for item in required):
        missing = ", ".join(item for item in required if item not in names)
        raise _host_error(f"archive is missing required entries: {missing}")
    if destination.exists() or destination.is_symlink():
        raise _host_error(f"extraction destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-unpack-", dir=destination.parent))
    try:
        try:
            result = subprocess.run(
                [_tar_path(), "-xf", str(archive), "-C", str(temporary)],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise _host_error(f"could not execute tar for extraction: {exc}") from exc
        if result.returncode != 0:
            raise _host_error(f"archive extraction failed: {(result.stderr or result.stdout).strip()}")
        extracted = temporary if expected_root == "." else temporary / expected_root
        _validate_tree(extracted)
        os.replace(extracted, destination)
    except HostRuntimeError:
        raise
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _host_install_root(state_root: Path, host_id: str, version: str) -> Path:
    _safe_name(host_id, "host_runtime_id")
    _safe_name(version, "version")
    return state_root / HOST_ROOT_NAME / host_id / version


def _pointer_for(host: dict) -> dict:
    return {
        "schema": SCHEMA,
        "host_runtime_id": host["host_runtime_id"],
        "version": host["version"],
        "manifest_sha256": host["manifest_sha256"],
    }


def _valid_pointer(value: object) -> dict | None:
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        return None
    try:
        host_id = _safe_name(value.get("host_runtime_id"), "current host_runtime_id")
        version = _safe_name(value.get("version"), "current version")
    except HostRuntimeError:
        return None
    digest = value.get("manifest_sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest.lower()):
        return None
    return {
        "schema": SCHEMA,
        "host_runtime_id": host_id,
        "version": version,
        "manifest_sha256": digest.lower(),
    }


def _same_pointer(left: object, right: object) -> bool:
    return _valid_pointer(left) == _valid_pointer(right)


def _history_entries(state_root: Path) -> list[dict]:
    value = _read_json(state_root / HOST_ROOT_NAME / HISTORY_FILE)
    if value.get("schema") != SCHEMA or not isinstance(value.get("entries"), list):
        return []
    return [pointer for item in value["entries"] if (pointer := _valid_pointer(item))]


def _activate_host(state_root: Path, host: dict) -> None:
    pointer_path = state_root / HOST_ROOT_NAME / CURRENT_FILE
    new_pointer = _pointer_for(host)
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
            _write_json(state_root / HOST_ROOT_NAME / HISTORY_FILE, {"schema": SCHEMA, "entries": entries[:16]})
    _write_json(pointer_path, new_pointer)


def _manifest_sha256(path: Path) -> str:
    return _sha256_file(path)


def verify_installed(
    path: str | Path,
    current: bool = False,
    validate_tree: bool = False,
) -> dict:
    root = _expand(path)
    manifest_path = root / MANIFEST_FILE
    result = {
        "root": str(root),
        "manifest": str(manifest_path),
        "current": current,
    }
    if root.is_symlink() or not root.is_dir():
        result.update(status="missing", ready=False, error="host runtime directory is missing")
        return result
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result.update(status="invalid", ready=False, error=f"host runtime manifest is unreadable: {exc}")
        return result
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        result.update(status="invalid", ready=False, error="host runtime manifest schema is not supported")
        return result
    try:
        host_id = _safe_name(manifest.get("host_runtime_id"), "host_runtime_id")
        version = _safe_name(manifest.get("version"), "version")
        provider = _safe_name(manifest.get("provider"), "provider")
        wine_root = _safe_relative(manifest.get("wine_root"), "wine_root")
        gptk_root = _safe_relative(manifest.get("gptk_root"), "gptk_root")
        prefix = _safe_relative(manifest.get("prefix"), "prefix")
    except HostRuntimeError as exc:
        result.update(status="invalid", ready=False, error=str(exc))
        return result
    result.update(
        {
            "schema": SCHEMA,
            "host_runtime_id": host_id,
            "version": version,
            "provider": provider,
            "release_tag": manifest.get("release_tag"),
            "manifest_sha256": _manifest_sha256(manifest_path),
            "wine_root": str(root / wine_root),
            "gptk_root": str(root / gptk_root),
            "prefix": str(root / prefix),
            "source": manifest.get("source", {}),
            "bridge_release": manifest.get("bridge_release", {}),
        }
    )
    checks = []
    required_paths = (
        ("wine", "Wine runtime", root / wine_root / "bin/wine", False),
        ("wineserver", "Wine server", root / wine_root / "bin/wineserver", False),
        ("wine-lib", "Wine libraries", root / wine_root / "lib/wine", True),
        ("wine-prefix", "Clean Wine prefix", root / prefix, True),
        ("wine-prefix-system-reg", "Wine prefix registry", root / prefix / "system.reg", False),
        ("gptk", "GPTK shared library", root / gptk_root / "external/libd3dshared.dylib", False),
        ("gptk-manifest", "GPTK manifest", root / gptk_root / "manifest.json", False),
    )
    for identifier, label, path_value, directory in required_paths:
        exists = path_value.is_dir() if directory else path_value.is_file()
        checks.append(
            {
                "id": identifier,
                "label": label,
                "status": "ready" if exists else "missing",
                "required": True,
                "path": str(path_value),
                "remediation": "Repair or reinstall the pinned host runtime." if not exists else "",
            }
        )
    if validate_tree:
        for candidate in (root / wine_root, root / gptk_root):
            if candidate.exists() and candidate.is_dir():
                try:
                    _validate_tree(candidate)
                except HostRuntimeError as exc:
                    checks.append(
                        {
                            "id": "runtime-tree",
                            "label": "Runtime symlink/layout safety",
                            "status": "missing",
                            "required": True,
                            "path": str(candidate),
                            "remediation": str(exc),
                        }
                    )
                    break
    result["checks"] = checks
    result["status"] = "ready" if all(item["status"] == "ready" for item in checks) else "incomplete"
    result["ready"] = result["status"] == "ready"
    return result


def current_host_runtime(state_root: str | Path, validate_tree: bool = False) -> dict | None:
    root = _expand(state_root)
    pointer_path = root / HOST_ROOT_NAME / CURRENT_FILE
    pointer = _read_json(pointer_path)
    if not pointer:
        return None
    valid = _valid_pointer(pointer)
    if not valid:
        return {
            "status": "invalid",
            "ready": False,
            "current": True,
            "error": "active host runtime pointer is invalid",
            "pointer": str(pointer_path),
        }
    install_root = _host_install_root(root, valid["host_runtime_id"], valid["version"])
    result = verify_installed(install_root, current=True, validate_tree=validate_tree)
    if result.get("manifest_sha256") != valid["manifest_sha256"]:
        result["status"] = "incomplete"
        result["ready"] = False
        result["error"] = "active host runtime pointer does not match its manifest"
    return result


def list_installed(state_root: str | Path) -> list[dict]:
    root = _expand(state_root) / HOST_ROOT_NAME
    current = current_host_runtime(state_root)
    current_key = (
        current.get("host_runtime_id"), current.get("version")
    ) if current else (None, None)
    result = []
    try:
        host_ids = sorted(root.iterdir())
    except OSError:
        return result
    for host_id in host_ids:
        if not host_id.is_dir() or host_id.is_symlink() or host_id.name.startswith("."):
            continue
        try:
            versions = sorted(host_id.iterdir())
        except OSError:
            continue
        for version in versions:
            if not version.is_dir() or version.is_symlink() or version.name.startswith("."):
                continue
            if not (version / MANIFEST_FILE).is_file():
                continue
            result.append(
                verify_installed(
                    version,
                    current=(host_id.name, version.name) == current_key,
                )
            )
    return result


def fetch_release(
    state_root: str | Path,
    tag: str | None = None,
    cache_dir: str | Path | None = None,
    releases_path: str | Path | None = None,
    wine_archive: str | Path | None = None,
    gptk_archive: str | Path | None = None,
) -> dict:
    """Fetch and atomically install a pinned Wine + GPTK host runtime."""

    release = release_for_tag(tag, releases_path)
    root = _expand(state_root)
    cache = _expand(cache_dir) if cache_dir else root / "downloads"
    wine_file, wine_verification = _ensure_cached(release["wine"], cache, wine_archive)
    gptk_file, gptk_verification = _ensure_cached(release["gptk"], cache, gptk_archive)
    install_root = _host_install_root(root, release["host_runtime_id"], release["version"])
    if install_root.exists() or install_root.is_symlink():
        existing = verify_installed(install_root)
        if existing.get("ready"):
            _activate_host(root, existing)
            existing["current"] = True
            return {
                "release": release,
                "wine_archive": wine_verification,
                "gptk_archive": gptk_verification,
                "host": existing,
            }
        raise _host_error(f"host runtime already exists with invalid contents: {install_root}")
    install_root.parent.mkdir(parents=True, exist_ok=True)
    if install_root.parent.is_symlink():
        raise _host_error(f"host runtime version directory is a symlink: {install_root.parent}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{release['version']}-staging-", dir=install_root.parent))
    try:
        _extract_component(wine_file, release["wine"], temporary / "wine")
        _extract_component(gptk_file, release["gptk"], temporary / "gptk")
        manifest = {
            "schema": SCHEMA,
            "host_runtime_id": release["host_runtime_id"],
            "version": release["version"],
            "provider": release["provider"],
            "release_tag": release["tag"],
            "wine_root": "wine",
            "gptk_root": "gptk",
            "prefix": "wine/prefix",
            "source": {
                "wine": release["wine"],
                "gptk": release["gptk"],
                "wine_archive": wine_verification,
                "gptk_archive": gptk_verification,
            },
            "wine_manifest": release.get("wine_manifest", {}),
            "bridge_release": release.get("bridge_release", {}),
            "installed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        _write_json(temporary / MANIFEST_FILE, manifest)
        staged = verify_installed(temporary, validate_tree=True)
        if not staged.get("ready"):
            raise _host_error(
                "staged host runtime failed verification: "
                + ", ".join(item["id"] for item in staged.get("checks", []) if item["status"] != "ready")
            )
        os.replace(temporary, install_root)
    except (OSError, HostRuntimeError):
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    installed = verify_installed(install_root, current=True)
    _activate_host(root, installed)
    return {
        "release": release,
        "wine_archive": wine_verification,
        "gptk_archive": gptk_verification,
        "host": installed,
    }
