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
import hashlib
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


def post_json(endpoint, payload, token):
    body = urllib.parse.urlencode({
        "access_token": token,
        "input_json": json.dumps(payload, separators=(",", ":")),
    }).encode()
    request = urllib.request.Request(
        f"https://api.steampowered.com/ICloudService/{endpoint}/v1/",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Ullage/0.1"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response).get("response", {})


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


def local_files(prefix, user, patterns, steam3_id):
    for pattern in patterns:
        root = pattern.get("root")
        base = CLOUD_PATH.resolve(prefix, user, root, str(pattern.get("path", "")).replace("{Steam3AccountID}", str(steam3_id)))
        if not base.exists():
            continue
        for candidate in base.rglob("*"):
            if candidate.is_file():
                relative = candidate.relative_to(base).as_posix()
                yield steam_filename(pattern, steam3_id) + "/" + relative, candidate


def sha1(filename):
    digest = hashlib.sha1()
    with filename.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def upload_files(appid, token, prefix, user, patterns, steam3_id, remote):
    remote_by_name = {item.get("filename"): item for item in remote}
    candidates = []
    for cloud_name, filename in local_files(prefix, user, patterns, steam3_id):
        digest = sha1(filename)
        if remote_by_name.get(cloud_name, {}).get("file_sha", "").lower() != digest:
            candidates.append((cloud_name, filename, digest))
    if not candidates:
        print("upload_candidates=0")
        return

    batch = post_json("BeginAppUploadBatch", {
        "appid": appid,
        "machine_name": "Ullage macOS",
        "files_to_upload": [name for name, _, _ in candidates],
        "files_to_delete": [],
    }, token)
    batch_id = batch.get("batch_id") or batch.get("batchid")
    if not batch_id:
        raise RuntimeError("Steam Cloud did not return an upload batch id")
    succeeded = False
    try:
        for cloud_name, filename, digest in candidates:
            data = filename.read_bytes()
            info = post_json("BeginHTTPUpload", {
                "appid": appid,
                "file_size": len(data),
                "filename": cloud_name,
                "file_sha": digest,
                "is_public": 0,
                "platforms_to_sync": ["all"],
                "upload_batch_id": batch_id,
            }, token)
            blocks = info.get("block_requests") or info.get("blockRequests") or []
            if not blocks and info.get("url_host"):
                blocks = [{"url_host": info["url_host"], "url_path": info.get("url_path", "/"), "block_offset": 0, "block_length": len(data), "request_headers": []}]
            for block in blocks:
                host = block.get("url_host") or block.get("urlHost")
                path = block.get("url_path") or block.get("urlPath")
                if not host or not path:
                    raise RuntimeError(f"Steam Cloud returned an unusable upload block for {cloud_name}")
                start = int(block.get("block_offset", block.get("blockOffset", 0)))
                length = int(block.get("block_length", block.get("blockLength", len(data) - start)))
                headers = {item.get("name"): item.get("value") for item in block.get("request_headers", block.get("requestHeaders", []))}
                request = urllib.request.Request(f"https://{host}{path}", data=data[start:start + length], headers=headers, method="PUT")
                with urllib.request.urlopen(request, timeout=60):
                    pass
            committed = post_json("CommitHTTPUpload", {
                "appid": appid, "transfer_succeeded": 1, "filename": cloud_name, "file_sha": digest,
            }, token)
            if committed.get("file_committed") is False:
                raise RuntimeError(f"Steam Cloud rejected {cloud_name}")
            print(f"uploaded={cloud_name}")
        succeeded = True
    finally:
        post_json("CompleteAppUploadBatch", {"appid": appid, "upload_batch_id": batch_id, "batch_result": 1 if succeeded else 2}, token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appid", required=True, type=int)
    parser.add_argument("--appinfo", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--steam3-account-id", required=True)
    parser.add_argument("--download", action="store_true", help="write matching cloud files into the prefix")
    parser.add_argument("--upload", action="store_true", help="upload changed local files (local-wins; explicit opt-in)")
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
    if args.upload:
        upload_files(args.appid, token, args.prefix, args.user, patterns, args.steam3_account_id, files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
