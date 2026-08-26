#!/usr/bin/env python3
"""Make native Steam Cloud resolve a Windows UFS root through a Wine prefix.

Native macOS Steam evaluates Auto-Cloud against the host platform selected for
the client.  When Ullage forces the client to select Windows depots, Windows
roots and the Windows-side forms of the all-platform roots need to point at
the same files inside the Wine prefix.  This small adapter adds a local
``os=Windows`` UFS root override and symlinks the corresponding MacAppSupport
path to the exact target directory.

The appinfo file must be edited while Steam is fully stopped.  The state file
records only entries and symlinks owned by Ullage, so restore can refuse to
overwrite a later Steam metadata change.
"""

import argparse
import copy
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
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
            r'"USERPROFILE"="C:\\\\users\\\\([^"\\]+)"',
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
    raise NativeCloudError(
        "cannot determine Wine user automatically; pass --cloud-wine-user"
    )


def resolve_steam_account_name(steam_root, requested, steam3_account_id):
    """Resolve the login name used by SteamCloudDocuments on Windows."""
    requested = str(requested or "").strip()
    if requested and requested.lower() != "auto":
        return requested

    if not steam_root:
        raise NativeCloudError(
            "SteamCloudDocuments needs --steam-root or --cloud-steam-account-name"
        )
    loginusers = Path(steam_root).expanduser() / "config" / "loginusers.vdf"
    try:
        text = loginusers.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise NativeCloudError(
            f"cannot read Steam login users: {loginusers}"
        ) from exc

    users = []
    for match in re.finditer(r'"(\d{17})"\s*\{([^{}]*)\}', text, re.DOTALL):
        account = re.search(r'"AccountName"\s+"((?:\\.|[^"\\])*)"', match.group(2))
        if account:
            name = re.sub(r"\\(.)", r"\1", account.group(1))
            users.append((match.group(1), name))

    if steam3_account_id:
        try:
            steam_id = str(76561197960265728 + int(steam3_account_id))
        except (TypeError, ValueError) as exc:
            raise NativeCloudError(
                f"invalid Steam3 account ID: {steam3_account_id}"
            ) from exc
        matches = [name for account_id, name in users if account_id == steam_id]
        if len(matches) == 1:
            return matches[0]
        raise NativeCloudError(
            f"Steam account ID {steam3_account_id} is not present in {loginusers}"
        )

    names = sorted({name for _, name in users})
    if len(names) == 1:
        return names[0]
    raise NativeCloudError(
        "cannot determine the Steam account name automatically; pass "
        "--cloud-steam-account-name"
    )


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


def unsupported_windows_roots(appinfo, appid):
    """Return unknown Windows-specific UFS roots instead of guessing them."""
    savefiles = app_ufs(appinfo, appid).get("savefiles", {})
    if not isinstance(savefiles, dict):
        return []
    roots = []
    for pattern in savefiles.values():
        if not isinstance(pattern, dict):
            continue
        root = pattern.get("root")
        if (
            isinstance(root, str)
            and (root.startswith("Win") or root.startswith("Windows"))
            and root not in CLOUD_PATH.ROOTS
            and root not in roots
        ):
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


def _parse_vdf_dict(tokens, index=0):
    """Parse the small quoted-dictionary subset used by remotecache.vdf."""
    if index >= len(tokens) or tokens[index] != "{":
        raise ValueError("VDF dictionary must start with an opening brace")
    result = {}
    index += 1
    while index < len(tokens) and tokens[index] != "}":
        key = tokens[index]
        index += 1
        if index >= len(tokens):
            raise ValueError("truncated VDF dictionary")
        if tokens[index] == "{":
            value, index = _parse_vdf_dict(tokens, index)
        else:
            value = tokens[index]
            index += 1
        result[key] = value
    if index >= len(tokens):
        raise ValueError("unterminated VDF dictionary")
    return result, index + 1


def _read_vdf_dict(filename):
    lexer = shlex.shlex(
        Path(filename).read_text(encoding="utf-8", errors="replace"),
        posix=True,
        punctuation_chars="{}",
    )
    lexer.whitespace_split = True
    tokens = list(lexer)
    if len(tokens) < 2 or tokens[1] != "{":
        raise ValueError("invalid VDF document")
    result, index = _parse_vdf_dict(tokens, 1)
    if index != len(tokens):
        raise ValueError("unexpected data after VDF document")
    return result


def _glob_regex(value):
    """Translate a slash-separated glob without letting * cross a segment."""
    escaped = re.escape(value)
    return escaped.replace(r"\*", "[^/]*").replace(r"\?", "[^/]")


def _expand_path_template(value):
    return re.sub(r"\{[^{}]+\}", "*", str(value or "").strip("/"))


def _savefile_matches(remote_name, rule):
    """Return whether a remote-cache path belongs to an Auto-Cloud rule."""
    path = _expand_path_template(rule.get("path", ""))
    pattern = str(rule.get("pattern", "*"))
    parent, separator, filename = remote_name.rpartition("/")
    path_re = _glob_regex(path)
    if rule.get("recursive"):
        parent_re = rf"{path_re}(?:/.*)?" if path_re else r".*"
        return bool(re.fullmatch(parent_re, parent)) and fnmatch.fnmatchcase(
            filename, pattern
        )
    return bool(re.fullmatch(path_re, parent)) and fnmatch.fnmatchcase(
        filename, pattern
    )


def _remote_cache_candidates(steam_root, appid, account_id):
    userdata = Path(steam_root).expanduser() / "userdata"
    if account_id:
        paths = [userdata / str(account_id) / str(appid) / "remotecache.vdf"]
    else:
        paths = sorted(userdata.glob(f"*/{appid}/remotecache.vdf"))
        if len(paths) != 1:
            return []
    return [path for path in paths if path.is_file()]


def _safe_remote_file(remote_root, name):
    source = (remote_root / Path(*str(name).split("/"))).resolve()
    try:
        source.relative_to(remote_root.resolve())
    except ValueError:
        return None
    return source if source.is_file() else None


def _sha1(filename):
    digest = hashlib.sha1()
    with Path(filename).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seed_local_remote_cache(
    steam_root,
    appid,
    prefix,
    wine_user,
    account_id,
    appinfo,
    install_dir=None,
    steam_account_name=None,
):
    """Seed only missing prefix files from Steam's already-local remote cache.

    This is a migration aid for stale ``remotecache.vdf`` root IDs.  It never
    downloads from Steam, overwrites an existing prefix file, or changes the
    remote cache; native Steam remains responsible for the actual sync.
    """
    if not steam_root:
        return []
    ufs = app_ufs(appinfo, appid)
    savefiles = ufs.get("savefiles", {})
    if not isinstance(savefiles, dict):
        return []
    rules = [
        item
        for item in savefiles.values()
        if isinstance(item, dict) and item.get("root") in CLOUD_PATH.ROOTS
    ]
    if not rules:
        return []

    seeded = []
    for cache_filename in _remote_cache_candidates(steam_root, appid, account_id):
        try:
            cache = _read_vdf_dict(cache_filename)
        except (OSError, ValueError):
            continue
        remote_root = cache_filename.parent / "remote"
        for remote_name, metadata in cache.items():
            if not isinstance(metadata, dict) or remote_name in {
                "ChangeNumber",
                "OSType",
            }:
                continue
            if not any(_savefile_matches(remote_name, rule) for rule in rules):
                continue
            source = _safe_remote_file(remote_root, remote_name)
            if source is None:
                continue
            try:
                expected_size = int(metadata.get("size", -1))
            except (TypeError, ValueError):
                continue
            if expected_size >= 0 and source.stat().st_size != expected_size:
                continue
            expected_sha = str(metadata.get("sha", "")).lower()
            if expected_sha and _sha1(source).lower() != expected_sha:
                continue
            root = next(
                rule["root"]
                for rule in rules
                if _savefile_matches(remote_name, rule)
            )
            target = CLOUD_PATH.resolve(
                prefix,
                wine_user,
                root,
                remote_name,
                install_dir,
                steam_account_name,
            )
            if target.exists() or target.is_symlink():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.ullage-seed")
            try:
                shutil.copy2(source, temporary)
                temporary.replace(target)
            finally:
                if temporary.exists():
                    temporary.unlink()
            seeded.append(str(target))
    return seeded


def install(
    appinfo_filename,
    appid,
    prefix,
    user,
    native_base,
    addpath_root,
    platform,
    state_out,
    steam_root=None,
    steam3_account_id="",
    install_dir=None,
    steam_account_name="",
):
    """Install overrides and symlinks, returning the recorded state."""
    appinfo_filename = Path(appinfo_filename).expanduser()
    prefix = Path(prefix).expanduser().resolve()
    if not prefix.is_dir() or not (prefix / "system.reg").is_file():
        raise NativeCloudError(f"Wine prefix is not initialized: {prefix}")
    addpath_root = normalize_addpath_root(addpath_root)
    appinfo = APPINFO.AppInfo(appinfo_filename)
    roots = supported_roots(appinfo, appid)
    unsupported = unsupported_windows_roots(appinfo, appid)
    if unsupported:
        raise NativeCloudError(
            "unsupported Windows Cloud root(s): " + ", ".join(unsupported)
        )
    if not roots:
        raise NativeCloudError(f"AppID {appid} has no supported Windows Cloud root")
    install_dir = Path(install_dir).expanduser().resolve() if install_dir else None
    if "gameinstall" in roots and (install_dir is None or not install_dir.is_dir()):
        raise NativeCloudError(
            "gameinstall Cloud root requires an existing Steam install directory"
        )
    if "SteamCloudDocuments" in roots:
        steam_account_name = resolve_steam_account_name(
            steam_root, steam_account_name, steam3_account_id
        )
    wine_user = resolve_wine_user(prefix, user)
    record = _cloud_record(appinfo, appid)
    ufs = record.setdefault("ufs", {})
    overrides = ufs.setdefault("rootoverrides", {})
    if not isinstance(overrides, dict):
        raise NativeCloudError("appinfo UFS rootoverrides is not a dictionary")

    entries = []
    created_links = []
    seeded_files = []
    original_data = bytes(appinfo.data)
    try:
        for root in roots:
            addpath = addpath_for(appid, root, len(roots), addpath_root)
            target = CLOUD_PATH.resolve(
                prefix,
                wine_user,
                root,
                install_dir=install_dir,
                steam_account_name=steam_account_name,
            )
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
        seeded_files = seed_local_remote_cache(
            steam_root,
            appid,
            prefix,
            wine_user,
            steam3_account_id,
            appinfo,
            install_dir,
            steam_account_name,
        )
        state = {
            "version": 1,
            "appid": int(appid),
            "platform": platform,
            "native_base": str(Path(native_base).expanduser()),
            "addpath_root": addpath_root.strip("/"),
            "prefix": str(prefix),
            "user": wine_user,
            "install_dir": str(install_dir) if install_dir else "",
            "steam_account_name": steam_account_name,
            "entries": entries,
            "seeded_files": seeded_files,
        }
        _write_json(state_out, state)
        return state
    except Exception:
        appinfo_filename.write_bytes(original_data)
        for link in reversed(created_links):
            if _same_target(link, Path(os.path.realpath(link))):
                link.unlink()
        raise


def restore(appinfo_filename, state_filename, expected_appid=None):
    """Restore only mappings still equal to the recorded generated values."""
    with Path(state_filename).expanduser().open(encoding="utf-8") as stream:
        state = json.load(stream)
    appid = int(state["appid"])
    if expected_appid is not None and appid != expected_appid:
        raise NativeCloudError(
            f"Cloud state AppID {appid} does not match requested AppID {expected_appid}"
        )
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
    install_parser.add_argument("--steam-root")
    install_parser.add_argument("--steam3-account-id", default="")
    install_parser.add_argument("--install-dir")
    install_parser.add_argument("--steam-account-name", default="")
    install_parser.add_argument("--state-out", required=True)

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--appinfo", required=True)
    restore_parser.add_argument("--state", required=True)
    restore_parser.add_argument("--appid", type=int)

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
                args.steam_root,
                args.steam3_account_id,
                args.install_dir,
                args.steam_account_name,
            )
            print(f"appid={state['appid']}")
            print(f"user={state['user']}")
            print("roots=" + ",".join(entry["root"] for entry in state["entries"]))
            print(f"seeded_files={len(state.get('seeded_files', []))}")
        else:
            state = restore(args.appinfo, args.state, expected_appid=args.appid)
            print(f"restored AppID {state['appid']}")
    except (APPINFO.AppInfoError, NativeCloudError, OSError, ValueError, KeyError) as exc:
        print(f"ullage-cloud-native: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
