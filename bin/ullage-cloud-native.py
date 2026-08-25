#!/usr/bin/env python3
"""Make native Steam Cloud resolve a Windows UFS root through a Wine prefix.

Native macOS Steam evaluates Auto-Cloud against the host platform selected for
the client.  When Ullage forces the client to select Windows depots, a
Windows-only ``WinAppData*`` root otherwise has no usable macOS path.  This
small adapter adds a local ``os=Windows`` UFS root override and symlinks the
corresponding MacAppSupport path to the exact Wine prefix directory.

The appinfo file must be edited while Steam is fully stopped.  The state file
records only entries and symlinks owned by Ullage, so restore can refuse to
overwrite a later Steam metadata change.
"""

import argparse
import copy
import importlib.util
import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


APPINFO = load_module("ullage_appinfo", "ullage-appinfo.py")
CLOUD_PATH = load_module("ullage_cloud_path", "ullage-cloud-path.py")


class NativeCloudError(Exception):
    """A safe, user-actionable native Cloud integration error."""


def resolve_wine_user(prefix, requested):
    """Resolve the Windows user directory used by this Wine prefix."""
    requested = str(requested or "").strip()
    if requested and requested.lower() != "auto":
        return requested

    prefix_path = Path(prefix).expanduser()
    user_reg = prefix_path / "user.reg"
    if user_reg.is_file():
        match = re.search(
            r'"USERPROFILE"="C:\\users\\([^"\\]+)"',
            user_reg.read_text(encoding="utf-8", errors="ignore"),
            re.IGNORECASE,
        )
        if match:
            return match.group(1)

    users_dir = prefix_path / "drive_c" / "users"
    candidates = sorted(
        item.name
        for item in users_dir.iterdir()
        if item.is_dir()
        and item.name.lower() not in {"public", "default", "default user", "all users"}
    ) if users_dir.is_dir() else []
    if "steamuser" in {item.lower() for item in candidates}:
        return next(item for item in candidates if item.lower() == "steamuser")
    if len(candidates) == 1:
        return candidates[0]
    return "steamuser"


def app_ufs(appinfo, appid):
    try:
        return appinfo.records[appid].sections["appinfo"].get("ufs", {})
    except KeyError as exc:
        raise NativeCloudError(f"AppID {appid} has no UFS section") from exc


def supported_roots(appinfo, appid):
    savefiles = app_ufs(appinfo, appid).get("savefiles", {})
    if not isinstance(savefiles, dict):
        return []
    roots = []
    for pattern in savefiles.values():
        if not isinstance(pattern, dict):
            continue
        root = pattern.get("root")
        if root in CLOUD_PATH.ROOTS and root not in roots:
            roots.append(root)
    return roots


def next_override_key(overrides):
    numeric = [int(key) for key in overrides if str(key).isdigit()]
    key = max(numeric, default=-1) + 1
    while str(key) in overrides:
        key += 1
    return str(key)


def normalize_addpath_root(value):
    parts = [part for part in str(value).strip("/").split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise NativeCloudError("native Cloud addpath root must be a relative directory")
    return "/".join(parts)


def override_for(root, platform, addpath):
    return {
        "root": root,
        "os": platform,
        "oscompare": "=",
        "useinstead": "MacAppSupport",
        "addpath": addpath,
    }


def addpath_for(appid, root, root_count, addpath_root):
    base = f"{addpath_root.strip('/')}/{appid}"
    if root_count > 1:
        base = f"{base}/{root}"
    return base


def link_for(native_base, addpath):
    # Keep this lexical path: resolving it would follow an existing symlink
    # and turn the link location into the Wine target.
    return Path(os.path.abspath(str(Path(native_base).expanduser() / Path(*addpath.split("/")))))


def _same_target(link, target):
    return link.is_symlink() and Path(os.path.realpath(link)) == target


def _write_json(filename, payload):
    filename = Path(filename).expanduser()
    filename.parent.mkdir(parents=True, exist_ok=True)
    temporary = filename.with_name(f".{filename.name}.ullage-tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        temporary.replace(filename)
    finally:
        if temporary.exists():
            temporary.unlink()


def _cloud_record(appinfo, appid):
    try:
        return appinfo.records[appid].sections["appinfo"]
    except KeyError as exc:
        raise NativeCloudError(f"AppID {appid} is not present in appinfo.vdf") from exc


def install(appinfo_filename, appid, prefix, user, native_base, addpath_root, platform, state_out):
    """Install overrides and symlinks, returning the recorded state."""
    appinfo_filename = Path(appinfo_filename).expanduser()
    prefix = Path(prefix).expanduser().resolve()
    if not prefix.is_dir() or not (prefix / "system.reg").is_file():
        raise NativeCloudError(f"Wine prefix is not initialized: {prefix}")
    addpath_root = normalize_addpath_root(addpath_root)
    appinfo = APPINFO.AppInfo(appinfo_filename)
    roots = supported_roots(appinfo, appid)
    if not roots:
        raise NativeCloudError(f"AppID {appid} has no supported Windows Cloud root")
    wine_user = resolve_wine_user(prefix, user)
    record = _cloud_record(appinfo, appid)
    ufs = record.setdefault("ufs", {})
    overrides = ufs.setdefault("rootoverrides", {})
    if not isinstance(overrides, dict):
        raise NativeCloudError("appinfo UFS rootoverrides is not a dictionary")

    entries = []
    created_links = []
    original_data = bytes(appinfo.data)
    try:
        for root in roots:
            addpath = addpath_for(appid, root, len(roots), addpath_root)
            target = CLOUD_PATH.resolve(prefix, wine_user, root)
            target.mkdir(parents=True, exist_ok=True)
            link = link_for(native_base, addpath)
            existing_key = None
            for key, item in overrides.items():
                if (
                    isinstance(item, dict)
                    and item.get("root") == root
                    and item.get("os") == platform
                    and item.get("oscompare", "=") == "="
                ):
                    existing_key = str(key)
                    break
            key = existing_key or next_override_key(overrides)
            original = copy.deepcopy(overrides.get(key)) if existing_key else None
            generated = override_for(root, platform, addpath)
            if link.exists() or link.is_symlink():
                if not _same_target(link, target):
                    raise NativeCloudError(
                        f"refusing to replace existing native Cloud path: {link}"
                    )
                link_owned = False
            else:
                link.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(str(target), str(link))
                created_links.append(link)
                link_owned = True
            overrides[key] = generated
            entries.append({
                "key": key,
                "root": root,
                "original": original,
                "generated": generated,
                "link": str(link),
                "target": str(target),
                "link_owned": link_owned,
            })

        appinfo.rewrite_record(appid)
        appinfo.write(appinfo_filename)
        state = {
            "version": 1,
            "appid": int(appid),
            "platform": platform,
            "native_base": str(Path(native_base).expanduser()),
            "addpath_root": addpath_root.strip("/"),
            "prefix": str(prefix),
            "user": wine_user,
            "entries": entries,
        }
        _write_json(state_out, state)
        return state
    except Exception:
        appinfo_filename.write_bytes(original_data)
        for link in reversed(created_links):
            if _same_target(link, Path(os.path.realpath(link))):
                link.unlink()
        raise


def restore(appinfo_filename, state_filename):
    """Restore only mappings still equal to the recorded generated values."""
    with Path(state_filename).expanduser().open(encoding="utf-8") as stream:
        state = json.load(stream)
    appid = int(state["appid"])
    appinfo_filename = Path(appinfo_filename).expanduser()
    appinfo = APPINFO.AppInfo(appinfo_filename)
    record = _cloud_record(appinfo, appid)
    overrides = record.get("ufs", {}).get("rootoverrides", {})
    if not isinstance(overrides, dict):
        raise NativeCloudError("appinfo UFS rootoverrides is not a dictionary")

    changed = False
    for entry in state.get("entries", []):
        key = str(entry["key"])
        current = overrides.get(key)
        if current != entry.get("generated"):
            raise NativeCloudError(
                f"Cloud override {key} changed after Ullage installed it; refusing restore"
            )
        original = entry.get("original")
        if original is None:
            del overrides[key]
        else:
            overrides[key] = original
        changed = True
    if changed:
        appinfo.rewrite_record(appid)
        appinfo.write(appinfo_filename)

    for entry in state.get("entries", []):
        if not entry.get("link_owned"):
            continue
        link = Path(entry["link"]).expanduser()
        target = Path(entry["target"]).expanduser().resolve()
        if link.is_symlink() and Path(os.path.realpath(link)) == target:
            link.unlink()
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--appinfo", required=True)
    install_parser.add_argument("--appid", required=True, type=int)
    install_parser.add_argument("--prefix", required=True)
    install_parser.add_argument("--user", default="auto")
    install_parser.add_argument(
        "--native-base",
        default=str(Path.home() / "Library" / "Application Support"),
    )
    install_parser.add_argument("--addpath-root", default="Ullage")
    install_parser.add_argument("--platform", default="Windows")
    install_parser.add_argument("--state-out", required=True)

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--appinfo", required=True)
    restore_parser.add_argument("--state", required=True)

    args = parser.parse_args()
    try:
        if args.operation == "install":
            state = install(
                args.appinfo,
                args.appid,
                args.prefix,
                args.user,
                args.native_base,
                args.addpath_root,
                args.platform,
                args.state_out,
            )
            print(f"appid={state['appid']}")
            print(f"user={state['user']}")
            print("roots=" + ",".join(entry["root"] for entry in state["entries"]))
        else:
            state = restore(args.appinfo, args.state)
            print(f"restored AppID {state['appid']}")
    except (APPINFO.AppInfoError, NativeCloudError, OSError, ValueError, KeyError) as exc:
        print(f"ullage-cloud-native: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
