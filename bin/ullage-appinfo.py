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
import os
import struct
import sys
from dataclasses import dataclass


APPINFO_28 = 0x107564428
APPINFO_29 = 0x107564429


class AppInfoError(Exception):
    pass


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
                if match is None or os.path.basename(current).lower() == match.lower():
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
        return selected, current

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
    patch.add_argument("--state-out")

    restore = subparsers.add_parser("restore")
    restore.add_argument("--state", required=True)
    restore.add_argument("--appinfo", required=True)

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
            if args.state_out:
                with open(args.state_out, "w", encoding="utf-8") as stream:
                    json.dump(state, stream, indent=2, sort_keys=True)
                    stream.write("\n")
            print(f"entry={entry}")
            print(f"original={original}")
            print(f"installed={args.replace}")
        else:
            with open(args.state, encoding="utf-8") as stream:
                state = json.load(stream)
            appinfo = AppInfo(args.appinfo)
            entry, current = appinfo.replace_launch(
                int(state["appid"]),
                state["original"],
                entry=str(state["entry"]),
                expect=state["installed"],
            )
            appinfo.write(args.appinfo)
            print(f"entry={entry}")
            print(f"restored={state['original']}")
    except (AppInfoError, OSError, ValueError, KeyError) as exc:
        print(f"ullage-appinfo: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
