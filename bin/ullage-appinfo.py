#!/usr/bin/env python3
"""Small, dependency-free editor for one Steam appinfo launch entry.

Steam's appcache is a binary VDF file. This intentionally supports only the
types needed to preserve and replace an existing config/launch executable;
unknown records are left byte-for-byte untouched. The caller must stop Steam
before replacing the file on disk.
"""

import argparse
import hashlib
import json
import ntpath
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


APPINFO_28 = 0x107564428
APPINFO_29 = 0x107564429


class AppInfoError(Exception):
    pass


def _depot_path(install_dir, windows_path):
    """Resolve a relative Windows path without leaving an install directory."""
    if not isinstance(windows_path, str) or not windows_path:
        return None
    normalized = windows_path.replace("\\", "/")
    if (
        ntpath.isabs(windows_path)
        or ntpath.splitdrive(windows_path)[0]
        or normalized.startswith("/")
    ):
        return None
    try:
        root = Path(install_dir).expanduser().resolve()
        candidate = root / normalized
        candidate.resolve(strict=False).relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate


@dataclass
class Record:
    appid: int
    start: int
    end: int
    header: dict
    sections: dict


class AppInfo:
    def __init__(self, filename):
        with open(filename, "rb") as stream:
            self.data = bytearray(stream.read())
        if len(self.data) < 16:
            raise AppInfoError("appinfo.vdf is truncated")
        self.version = struct.unpack_from("<Q", self.data, 0)[0]
        if self.version not in (APPINFO_28, APPINFO_29):
            raise AppInfoError(f"unsupported appinfo version: {self.version:#x}")
        self.pool = []
        self.pool_count = 0
        if self.version == APPINFO_29:
            self.string_offset = struct.unpack_from("<q", self.data, 8)[0]
            if not 16 <= self.string_offset <= len(self.data) - 4:
                raise AppInfoError("invalid appinfo string-table offset")
            self._read_pool()
            limit = self.string_offset
        else:
            self.string_offset = None
            limit = len(self.data)
        self.records = self._read_records(limit)

    def _read_pool(self):
        offset = self.string_offset
        count = struct.unpack_from("<I", self.data, offset)[0]
        offset += 4
        for _ in range(count):
            end = self.data.find(b"\0", offset)
            if end < 0:
                raise AppInfoError("unterminated appinfo string-table entry")
            self.pool.append(self._decode(self.data[offset:end]))
            offset = end + 1
        self.pool_count = len(self.pool)

    @staticmethod
    def _decode(raw):
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1") + "\x06"

    @staticmethod
    def _encode_string(value):
        if value.endswith("\x06"):
            raw = value[:-1].encode("latin-1")
        else:
            raw = value.encode("utf-8")
        return raw + b"\0"

    def _read_value(self, offset, value_type):
        if value_type == 0:
            return self._read_dict(offset)
        if value_type == 1:
            end = self.data.find(b"\0", offset)
            if end < 0:
                raise AppInfoError("unterminated appinfo string")
            return self._decode(self.data[offset:end]), end + 1
        if value_type == 2:
            return struct.unpack_from("<I", self.data, offset)[0], offset + 4
        raise AppInfoError(f"unsupported appinfo value type: {value_type}")

    def _read_key(self, offset):
        if self.version == APPINFO_29:
            index = struct.unpack_from("<I", self.data, offset)[0]
            try:
                return self.pool[index], offset + 4
            except IndexError as exc:
                raise AppInfoError(f"invalid appinfo string-pool index: {index}") from exc
        end = self.data.find(b"\0", offset)
        if end < 0:
            raise AppInfoError("unterminated appinfo key")
        return self._decode(self.data[offset:end]), end + 1

    def _read_dict(self, offset):
        result = {}
        while True:
            if offset >= len(self.data):
                raise AppInfoError("unterminated appinfo dictionary")
            value_type = self.data[offset]
            offset += 1
            if value_type == 8:
                return result, offset
            key, offset = self._read_key(offset)
            value, offset = self._read_value(offset, value_type)
            result[key] = value

    def _read_records(self, limit):
        records = {}
        offset = 16
        header_size = struct.calcsize("<4IQ20sI20s")
        while offset + header_size <= limit:
            start = offset
            values = struct.unpack_from("<4IQ20sI20s", self.data, offset)
            offset += header_size
            header = {
                "appid": values[0],
                "size": values[1],
                "state": values[2],
                "last_update": values[3],
                "access_token": values[4],
                "checksum_text": values[5],
                "change_number": values[6],
                "checksum_binary": values[7],
            }
            if header["appid"] == 0:
                break
            sections, offset = self._read_dict(offset)
            records[header["appid"]] = Record(
                header["appid"], start, offset, header, sections
            )
        return records

    def _encode_key(self, key):
        if self.version == APPINFO_29:
            try:
                index = self.pool.index(key)
            except ValueError:
                self.pool.append(key)
                index = len(self.pool) - 1
            return struct.pack("<I", index)
        return self._encode_string(key)

    def _encode_dict(self, value):
        encoded = bytearray()
        for key, item in value.items():
            if isinstance(item, dict):
                encoded.extend(b"\0")
                encoded.extend(self._encode_key(key))
                encoded.extend(self._encode_dict(item))
            elif isinstance(item, str):
                encoded.extend(b"\1")
                encoded.extend(self._encode_key(key))
                encoded.extend(self._encode_string(item))
            elif isinstance(item, int):
                encoded.extend(b"\2")
                encoded.extend(self._encode_key(key))
                encoded.extend(struct.pack("<I", item))
            else:
                raise AppInfoError(f"unsupported value for key {key!r}")
        encoded.append(8)
        return bytes(encoded)

    def _dict_to_text(self, value, depth=0):
        output = bytearray()
        indent = b"\t" * depth
        for key, item in value.items():
            key_bytes = key.replace("\\", "\\\\").encode("utf-8")
            if isinstance(item, dict):
                output.extend(indent + b'"' + key_bytes + b'"\n')
                output.extend(indent + b"{\n")
                output.extend(self._dict_to_text(item, depth + 1))
                output.extend(indent + b"}\n")
            else:
                if isinstance(item, str) and item.endswith("\x06"):
                    value_bytes = item[:-1].encode("latin-1")
                else:
                    value_bytes = str(item).encode("utf-8")
                output.extend(
                    indent + b'"' + key_bytes + b'"\t\t"' + value_bytes + b'"\n'
                )
        return bytes(output)

    def rewrite_record(self, appid):
        """Re-encode one app record after a structured section edit."""
        try:
            record = self.records[appid]
        except KeyError as exc:
            raise AppInfoError(f"AppID {appid} is not present in appinfo.vdf") from exc

        encoded_sections = self._encode_dict(record.sections)
        header = dict(record.header)
        header["size"] = len(encoded_sections) + struct.calcsize("<4IQ20sI20s") - 8
        header["checksum_text"] = hashlib.sha1(self._dict_to_text(record.sections)).digest()
        header["checksum_binary"] = hashlib.sha1(encoded_sections).digest()
        encoded_header = struct.pack(
            "<4IQ20sI20s",
            header["appid"],
            header["size"],
            header["state"],
            header["last_update"],
            header["access_token"],
            header["checksum_text"],
            header["change_number"],
            header["checksum_binary"],
        )
        replacement = encoded_header + encoded_sections
        old_string_offset = self.string_offset
        self.data[record.start:record.end] = replacement
        if self.version == APPINFO_29:
            new_string_offset = old_string_offset + len(replacement) - (record.end - record.start)
            additions = self.pool[self.pool_count:]
            if additions:
                self.data.extend(b"".join(self._encode_string(item) for item in additions))
            struct.pack_into("<q", self.data, 8, new_string_offset)
            struct.pack_into("<I", self.data, new_string_offset, len(self.pool))

    def replace_launch(self, appid, executable, match=None, entry=None, expect=None):
        try:
            record = self.records[appid]
        except KeyError as exc:
            raise AppInfoError(f"AppID {appid} is not present in appinfo.vdf") from exc
        try:
            launch = record.sections["appinfo"]["config"]["launch"]
        except KeyError as exc:
            raise AppInfoError(f"AppID {appid} has no config/launch section") from exc

        selected = None
        if entry is not None:
            selected = str(entry)
            if selected not in launch:
                raise AppInfoError(f"launch entry {selected} is not present")
        else:
            for key, item in launch.items():
                current = item.get("executable") if isinstance(item, dict) else None
                if not isinstance(current, str):
                    continue
                current_name = current.replace("\\", "/").rsplit("/", 1)[-1]
                if match is None or current_name.lower() == match.lower():
                    selected = key
                    break
            if selected is None:
                raise AppInfoError(f"no launch entry matches {match!r}")

        current = launch[selected].get("executable")
        if not isinstance(current, str):
            raise AppInfoError(f"launch entry {selected} has no executable")
        if expect is not None and current != expect:
            raise AppInfoError(
                f"launch entry {selected} changed unexpectedly: {current!r} != {expect!r}"
            )
        launch[selected]["executable"] = executable
        self.rewrite_record(appid)
        return selected, current

    def windows_launches(self, appid, install_dir=None):
        """Return executable launch entries that belong to the Windows depot."""
        try:
            app = self.records[appid].sections["appinfo"]
            common = app.get("common", {})
            launch = app["config"]["launch"]
        except (KeyError, TypeError) as exc:
            raise AppInfoError(f"AppID {appid} has no config/launch section") from exc

        common_os = common.get("oslist")
        result = []
        for key, item in launch.items():
            entry = str(key)
            if not entry.isascii() or not entry.isdigit():
                continue
            if not isinstance(item, dict) or not isinstance(item.get("executable"), str):
                continue
            executable = item["executable"]
            if not executable.lower().endswith(".exe"):
                continue
            entry_config = item.get("config", {})
            entry_os = entry_config.get("oslist") if isinstance(entry_config, dict) else None
            oslist = entry_os if entry_os is not None else common_os
            if oslist is not None and "windows" not in {
                value.strip().lower() for value in str(oslist).split(",")
            }:
                continue
            workingdir = item.get("workingdir", "")
            if not isinstance(workingdir, str):
                workingdir = ""
            if install_dir is not None:
                candidate = _depot_path(install_dir, executable)
                if candidate is None or not candidate.is_file() or candidate.is_symlink():
                    continue
                if workingdir:
                    working_path = _depot_path(install_dir, workingdir)
                    if (
                        working_path is None
                        or not working_path.is_dir()
                        or working_path.is_symlink()
                    ):
                        continue
            result.append(
                {
                    "entry": entry,
                    "executable": executable,
                    "workingdir": workingdir,
                }
            )
        if not result:
            raise AppInfoError(f"AppID {appid} has no Windows .exe launch entries")
        return result

    def replace_launches(self, appid, replacements, expects=None):
        """Replace several launch entries in one record rewrite."""
        try:
            launch = self.records[appid].sections["appinfo"]["config"]["launch"]
        except (KeyError, TypeError) as exc:
            raise AppInfoError(f"AppID {appid} has no config/launch section") from exc

        changed = []
        for entry, executable in replacements:
            selected = str(entry)
            if selected not in launch:
                raise AppInfoError(f"launch entry {selected} is not present")
            current = launch[selected].get("executable")
            if not isinstance(current, str):
                raise AppInfoError(f"launch entry {selected} has no executable")
            if expects is not None and current != expects.get(selected):
                raise AppInfoError(
                    f"launch entry {selected} changed unexpectedly: "
                    f"{current!r} != {expects.get(selected)!r}"
                )
            launch[selected]["executable"] = executable
            changed.append((selected, current, executable))
        if not changed:
            raise AppInfoError(f"AppID {appid} has no launch entries to replace")
        self.rewrite_record(appid)
        return changed

    def restore_launch(self, appid, original, entry, installed):
        """Restore a recorded launch entry, accepting an existing restore."""
        try:
            record = self.records[appid]
            launch = record.sections["appinfo"]["config"]["launch"]
            selected = str(entry)
            current = launch[selected]["executable"]
        except (KeyError, TypeError) as exc:
            raise AppInfoError(
                f"launch entry {entry} is not present or has no executable"
            ) from exc

        if current == original:
            return selected, current, False
        if current != installed:
            raise AppInfoError(
                f"launch entry {selected} changed unexpectedly: "
                f"{current!r} != {installed!r}"
            )
        launch[selected]["executable"] = original
        self.rewrite_record(appid)
        return selected, current, True

    def restore_state(self, state, expected_appid=None):
        """Restore a legacy single-entry or multi-entry mapping state."""
        entries = state.get("entries")
        if entries is None:
            entries = [state]
        if not isinstance(entries, list) or not entries:
            raise AppInfoError("mapping state has no launch entries")
        try:
            appid = int(state["appid"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AppInfoError("mapping state has invalid AppID or launch section") from exc
        if expected_appid is not None and appid != expected_appid:
            raise AppInfoError(
                f"mapping state AppID {appid} does not match requested AppID {expected_appid}"
            )
        try:
            launch = self.records[appid].sections["appinfo"]["config"]["launch"]
        except (KeyError, TypeError) as exc:
            raise AppInfoError("mapping state has invalid AppID or launch section") from exc

        results = []
        changes = []
        for item in entries:
            if not isinstance(item, dict):
                raise AppInfoError("mapping state has an invalid launch entry")
            try:
                selected = str(item["entry"])
                original = item["original"]
                installed = item["installed"]
                current = launch[selected]["executable"]
            except (KeyError, TypeError) as exc:
                raise AppInfoError(
                    f"launch entry {item.get('entry', '?')} is not present or has no executable"
                ) from exc
            if not isinstance(original, str) or not isinstance(installed, str):
                raise AppInfoError(f"mapping state has invalid executable for entry {selected}")
            if current == original:
                changed = False
            elif current == installed:
                changes.append((selected, original))
                changed = True
            else:
                raise AppInfoError(
                    f"launch entry {selected} changed unexpectedly: "
                    f"{current!r} != {installed!r}"
                )
            results.append((selected, current, changed, original))

        if changes:
            for selected, original in changes:
                launch[selected]["executable"] = original
            self.rewrite_record(appid)
        return results

    def write(self, filename):
        with open(filename, "wb") as stream:
            stream.write(self.data)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)

    patch = subparsers.add_parser("patch")
    patch.add_argument("--appinfo", required=True)
    patch.add_argument("--appid", required=True, type=int)
    patch.add_argument("--replace", required=True)
    patch.add_argument("--match")
    patch.add_argument("--entry")
    patch.add_argument("--expect")
    patch.add_argument("--launcher")
    patch.add_argument("--state-out")

    patch_all = subparsers.add_parser("patch-all")
    patch_all.add_argument("--appinfo", required=True)
    patch_all.add_argument("--appid", required=True, type=int)
    patch_all.add_argument("--replace-template", required=True)
    patch_all.add_argument("--launcher-template")
    patch_all.add_argument("--install-dir")
    patch_all.add_argument("--state-out", required=True)

    list_windows = subparsers.add_parser("list-windows")
    list_windows.add_argument("--appinfo", required=True)
    list_windows.add_argument("--appid", required=True, type=int)
    list_windows.add_argument("--install-dir")

    restore = subparsers.add_parser("restore")
    restore.add_argument("--state", required=True)
    restore.add_argument("--appinfo", required=True)
    restore.add_argument("--appid", type=int)

    state_launchers = subparsers.add_parser("state-launchers")
    state_launchers.add_argument("--state", required=True)

    args = parser.parse_args()
    try:
        if args.operation == "patch":
            appinfo = AppInfo(args.appinfo)
            entry, original = appinfo.replace_launch(
                args.appid,
                args.replace,
                match=args.match,
                entry=args.entry,
                expect=args.expect,
            )
            appinfo.write(args.appinfo)
            state = {
                "appid": args.appid,
                "entry": entry,
                "original": original,
                "installed": args.replace,
            }
            if args.launcher:
                state["launcher"] = args.launcher
            if args.state_out:
                with open(args.state_out, "w", encoding="utf-8") as stream:
                    json.dump(state, stream, indent=2, sort_keys=True)
                    stream.write("\n")
            print(f"entry={entry}")
            print(f"original={original}")
            print(f"installed={args.replace}")
        elif args.operation == "patch-all":
            appinfo = AppInfo(args.appinfo)
            launches = appinfo.windows_launches(args.appid, args.install_dir)
            replacements = [
                (item["entry"], args.replace_template.format(entry=item["entry"]))
                for item in launches
            ]
            changed = appinfo.replace_launches(args.appid, replacements)
            appinfo.write(args.appinfo)
            entries = []
            for item, (_, original, installed) in zip(launches, changed):
                state_entry = {
                    "entry": item["entry"],
                    "original": original,
                    "installed": installed,
                }
                if args.launcher_template:
                    state_entry["launcher"] = args.launcher_template.format(
                        entry=item["entry"]
                    )
                entries.append(state_entry)
            with open(args.state_out, "w", encoding="utf-8") as stream:
                json.dump({"appid": args.appid, "entries": entries}, stream, indent=2, sort_keys=True)
                stream.write("\n")
            print(f"entries={len(entries)}")
        elif args.operation == "list-windows":
            appinfo = AppInfo(args.appinfo)
            for item in appinfo.windows_launches(args.appid, args.install_dir):
                executable = item["executable"].replace("\\", "/")
                workingdir = item["workingdir"].replace("\\", "/")
                print(f"{item['entry']}\t{executable}\t{workingdir}")
        elif args.operation == "state-launchers":
            with open(args.state, encoding="utf-8") as stream:
                state = json.load(stream)
            entries = state.get("entries") or [state]
            for item in entries:
                launcher = item.get("launcher")
                if launcher:
                    print(launcher)
        else:
            with open(args.state, encoding="utf-8") as stream:
                state = json.load(stream)
            appinfo = AppInfo(args.appinfo)
            results = appinfo.restore_state(state, expected_appid=args.appid)
            if any(item[2] for item in results):
                appinfo.write(args.appinfo)
            for entry, current, changed, original in results:
                print(f"entry={entry}")
                label = "restored" if changed else "already_restored"
                print(f"{label}={original}")
    except (AppInfoError, OSError, ValueError, KeyError) as exc:
        print(f"ullage-appinfo: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
