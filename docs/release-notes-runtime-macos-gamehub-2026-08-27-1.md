# Ullage GameHub host runtime 2026-08-27-1

This is an experimental, exact-byte host-runtime option for the Ullage
macOS/Steam bridge. It reproduces the clean GameHub Wine Proton 11.0 payload
used by the current x86_64 matrix, plus a pinned acquisition record for Apple
GPTK 3.0-3.

Included in this release:

* `wine-proton_11.0_0728.tar.zst` — the original clean GameHub
  Wine archive, uploaded byte-for-byte and verified against SHA-256
  `e72b9016c1732955dc5b24a93e8c11e5611b9454e8e7cf1a04a68f1dd3f06fd0`.
* `host-releases.json` — the Ullage lock containing the Wine and GPTK source
  URLs, sizes, hashes, prefix layout, and matching bridge release.

GPTK/D3DMetal is not uploaded here. `ullagectl runtime host-fetch` obtains the
exact GPTK archive from the locked original GameHub source, or accepts an exact
local archive with `--gptk-archive PATH`. The release intentionally excludes
GameHub.app, its proprietary SandboxFS library, native Steam, and all private
virtual prefixes.

Install on a machine without GameHub installed:

```sh
bin/ullagectl runtime fetch --json
bin/ullagectl runtime host-fetch --json
bin/ullagectl runtime host-verify --json
```

This is a tested provider snapshot, not a source-built Wine distribution and
not a universal renderer guarantee. The source-built successor is tracked in
`docs/runtime-providers.md`.
