#!/usr/bin/env python3
"""Verify and stage user-owned Windows Steam client support files.

Valve's Windows Steam client DLLs are not redistributable Ullage runtime
artifacts.  This helper makes the user-supplied import explicit, repeatable,
and auditable without making the launch path depend on the provider that
originally supplied the files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = 1
ARCH_FILES = {
    "win32": ("steam.dll", "steamclient.dll", "tier0_s.dll", "vstdlib_s.dll"),
    "win64": ("steamclient64.dll", "tier0_s64.dll", "vstdlib_s64.dll"),
}


class SteamClientError(ValueError):
    """A user-facing Steam client import error."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _case_insensitive_file(root: Path, name: str) -> Path | None:
    direct = root / name
    if direct.is_file() and not direct.is_symlink():
        return direct
    wanted = name.lower()
    try:
        for candidate in root.iterdir():
            if candidate.name.lower() == wanted and candidate.is_file() and not candidate.is_symlink():
                return candidate
    except OSError as exc:
        raise SteamClientError(f"cannot read Steam client root: {root}: {exc}") from exc
    return None


def inspect_root(source_root: str | Path, arch: str) -> dict:
    root = Path(source_root).expanduser()
    if arch not in ARCH_FILES:
        raise SteamClientError(f"unsupported Windows architecture: {arch}")
    if root.is_symlink() or not root.is_dir():
        raise SteamClientError(f"Steam client root is missing or not a directory: {root}")
    files = []
    missing = []
    for name in ARCH_FILES[arch]:
        source = _case_insensitive_file(root, name)
        if source is None:
            missing.append(name)
            continue
        try:
            stat = source.stat()
            files.append(
                {
                    "path": name,
                    "source": str(source),
                    "size": stat.st_size,
                    "sha256": sha256(source),
                }
            )
        except OSError as exc:
            raise SteamClientError(f"cannot read Steam client file: {source}: {exc}") from exc
    if missing:
        raise SteamClientError(
            f"Steam client root is missing {arch} support files: {', '.join(missing)}"
        )
    return {
        "schema": SCHEMA,
        "kind": "user-owned-steam-client",
        "source_root": str(root.resolve()),
        "architecture": arch,
        "files": files,
    }


def write_manifest(record: dict, path: str | Path) -> Path:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def stage(
    source_root: str | Path,
    prefix: str | Path,
    arch: str,
    manifest_path: str | Path | None = None,
) -> dict:
    record = inspect_root(source_root, arch)
    prefix_path = Path(prefix).expanduser()
    if prefix_path.is_symlink() or not prefix_path.is_dir():
        raise SteamClientError(f"Wine prefix is missing or not a directory: {prefix_path}")
    steam_dir = prefix_path / "drive_c" / "Program Files (x86)" / "Steam"
    steam_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    staged = []
    for item in record["files"]:
        source = Path(item["source"])
        target = steam_dir / item["path"]
        if target.is_symlink():
            raise SteamClientError(f"Steam client target must not be a symlink: {target}")
        backup = None
        if target.exists():
            if target.is_dir():
                raise SteamClientError(f"Steam client target is a directory: {target}")
            if sha256(target) == item["sha256"]:
                staged.append({"path": item["path"], "target": str(target), "action": "unchanged"})
                continue
            backup_path = target.with_name(f"{target.name}.ullage-original-{stamp}")
            counter = 1
            while backup_path.exists():
                backup_path = target.with_name(f"{target.name}.ullage-original-{stamp}-{counter}")
                counter += 1
            shutil.copy2(target, backup_path)
            backup = str(backup_path)
        temporary = Path(tempfile.mkstemp(prefix=f".{target.name}.", dir=str(steam_dir))[1])
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        staged.append({"path": item["path"], "target": str(target), "action": "staged", "backup": backup})
    manifest = None
    if manifest_path:
        manifest = write_manifest(record, manifest_path)
    return {"manifest": str(manifest) if manifest else None, "source": record, "staged": staged}


def main() -> int:
    parser = argparse.ArgumentParser(prog="ullage-steam-client")
    parser.add_argument("command", choices=("inspect", "stage"))
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--arch", choices=tuple(ARCH_FILES), required=True)
    parser.add_argument("--prefix")
    parser.add_argument("--manifest")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            result = {"source": inspect_root(args.source_root, args.arch)}
        else:
            if not args.prefix:
                raise SteamClientError("stage requires --prefix")
            result = stage(args.source_root, args.prefix, args.arch, args.manifest)
    except (OSError, SteamClientError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
