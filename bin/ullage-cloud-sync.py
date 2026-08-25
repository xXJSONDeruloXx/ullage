#!/usr/bin/env python3
"""Synchronize Windows Auto Cloud files into an Ullage Wine prefix.

The native macOS Steam client cannot resolve Windows UFS roots.  This tool
uses Steam's documented ICloudService read path and the prefix resolver, while
leaving Steam's appinfo and launcher state untouched.  Upload support is
intentionally not enabled until conflict handling is proven.
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import importlib.util

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ullage_appinfo", ROOT / "ullage-appinfo.py")
APPINFO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APPINFO)
SPEC = importlib.util.spec_from_file_location("ullage_cloud_path", ROOT / "ullage-cloud-path.py")
CLOUD_PATH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLOUD_PATH)


def cloud_patterns(appinfo, appid):
    record = appinfo.records[appid].sections["appinfo"]
    ufs = record.get("ufs", {})
    savefiles = ufs.get("savefiles", {})
    if not isinstance(savefiles, dict):
        return []
    return [item for item in savefiles.values() if isinstance(item, dict)]


def steam_filename(pattern, steam3_id):
    root = pattern.get("root")
    path = str(pattern.get("path", ""))
    path = path.replace("{Steam3AccountID}", str(steam3_id))
    path = path.replace("{64BitSteamID}", str(steam3_id))
    return f"%{root}%{path}".replace("\\", "/").rstrip("/")


def request_json(url, params, token):
    query = urllib.parse.urlencode({"access_token": token, **params})
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "Ullage/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def enumerate_files(appid, token):
    payload = request_json(
        "https://api.steampowered.com/ICloudService/EnumerateUserFiles/v1/",
        {"appid": appid, "extended_details": 1},
        token,
    )
    return payload.get("response", payload).get("files", [])


def safe_destination(prefix, user, filename, patterns, steam3_id):
    normalized = filename.replace("\\", "/")
    for pattern in patterns:
        cloud_prefix = steam_filename(pattern, steam3_id)
        if normalized == cloud_prefix or normalized.startswith(cloud_prefix + "/"):
            relative = normalized[len(cloud_prefix):].lstrip("/")
            return CLOUD_PATH.resolve(prefix, user, pattern["root"], pattern.get("path", "").replace("{Steam3AccountID}", str(steam3_id)) + "/" + relative)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appid", required=True, type=int)
    parser.add_argument("--appinfo", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--steam3-account-id", required=True)
    parser.add_argument("--download", action="store_true", help="write matching cloud files into the prefix")
    args = parser.parse_args()
    token = os.environ.get("ULLAGE_STEAM_ACCESS_TOKEN", "").strip()
    if not token:
        print("ullage-cloud-sync: set ULLAGE_STEAM_ACCESS_TOKEN (read_cloud scope)", file=sys.stderr)
        return 2

    appinfo = APPINFO.AppInfo(args.appinfo)
    patterns = cloud_patterns(appinfo, args.appid)
    files = enumerate_files(args.appid, token)
    matched = 0
    for item in files:
        destination = safe_destination(args.prefix, args.user, item.get("filename", ""), patterns, args.steam3_account_id)
        if destination is None:
            continue
        matched += 1
        print(f"file={item.get('filename')} sha={item.get('file_sha', '')} destination={destination}")
        if args.download:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(item["url"], timeout=60) as source, destination.open("wb") as target:
                target.write(source.read())
    print(f"matched={matched}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
