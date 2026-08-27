# Runtime contract

Ullage deliberately does not vendor native Steam, a private game prefix, or
GameHub's proprietary SandboxFS library. The small lsteamclient bridge can be
installed as a versioned, checksum-verified package. The exact tested GameHub
Wine/GPTK stack is also available as a pinned host-runtime option, but GPTK
remains an original-source/user-supplied component because its Apple-signed
D3DMetal payload is not an Ullage-owned redistributable. A source-built Wine
successor is tracked separately in [`docs/runtime-providers.md`](../docs/runtime-providers.md).

The current bridge expects:

* WINE_ROOT/bin/wine
* WINE_ROOT/bin/wineserver
* WINE_ROOT/lib/wine
* GPTK_ROOT/external/libd3dshared.dylib
* BRIDGE_ROOT/x86_64-unix/lsteamclient.so
* BRIDGE_ROOT/x86_64-windows/lsteamclient.dll
* BRIDGE_ROOT/i386-windows/lsteamclient.dll for 32-bit games
* BRIDGE_ROOT/x86_64-windows/steamclient64.dll for 64-bit Steamworks games

The lsteamclient pair is the Wine-side Steam transport built from a compatible
Proton/Wine source tree. On Apple Silicon, the currently tested third-party
Wine runtime is x86_64 under Rosetta; an arm64-native Wine runtime is a future
target, not an assumption made by this repository.

The optional `steamclient64.dll` is a small canonical-name forwarder, not a
second Steam client. Wine can load the Proton lsteamclient image as
`lsteamclient.dll`, but loading that same image by the game's requested name
`steamclient64.dll` can stall before `SteamAPI_Init` returns on x86_64. Build
the forwarder from the [ullage-patches](https://github.com/xXJSONDeruloXx/ullage-patches)
repository and stage it at:

```text
PREFIX/drive_c/Program Files (x86)/Steam/steamclient64.dll
```

When the forwarder is present under `BRIDGE_ROOT`, Ullage verifies that the
prefix copy matches it and fails early if the runtime was staged incorrectly.
The bridge never overwrites a prefix DLL during launch.

The maintainable macOS portability patch set and its exact upstream pin live in
the separate [ullage-patches](https://github.com/xXJSONDeruloXx/ullage-patches)
repository. Ullage does not fork or vendor that source tree.

The native Steam client remains the source of steamclient.dylib, loader
environment, IPC descriptors, user/session state, and overlay services. Ullage
only passes those through the Wine launch boundary.

The bridge keeps `BRIDGE_ROOT` as the first `WINEDLLPATH` entry, followed by
the GPTK and Wine runtime paths. Do not prepend the package's
`x86_64-windows` or `i386-windows` subdirectory: in the tested GameHub Wine
environment that ordering makes x64 `lsteamclient` initialization fail before
the game can render. The launch bridge passes `WINEPREFIX_BASE`, `WINEARCH`,
and the computed `DYLD_INSERT_LIBRARIES` directly to Wine so the native Steam
transport is not altered by an intermediate shell.

## Versioned bridge package

`ullage-patches` produces a package containing the four bridge files listed
above and a `manifest.json` with the package version, exact source commit,
file sizes, and SHA-256 digests. It intentionally does not contain Wine,
GPTK/D3DMetal, native Steam, or a prefix. This keeps the downloaded artifact
small while making the manually assembled bridge reproducible and auditable.

After extracting a package, install it with the stable CLI:

```sh
bin/ullagectl runtime install \
  --manifest /path/to/ullage-bridge-runtime-VERSION/manifest.json
bin/ullagectl runtime verify
```

On a new machine, use the checked-in public-release lock instead of manually
assembling the four files:

```sh
bin/ullagectl runtime releases --json
bin/ullagectl runtime fetch --json
bin/ullagectl runtime verify --json
```

`runtime fetch` downloads the pinned GitHub release over HTTPS, checks the
locked archive size and SHA-256, rejects path traversal, symlink, hard-link,
device, and oversized archive members, then verifies the extracted manifest
and every artifact before atomic installation. The release URL, tag, asset,
size, and digest are recorded in [`releases.json`](releases.json). The archive
is cached under `~/.ullage/downloads` by default; pass `--cache-dir` for an
external volume.

The installer verifies every artifact before copying, copies into a temporary
versioned directory under `~/.ullage/runtimes`, verifies the copy again, and
only then atomically updates `~/.ullage/runtimes/current.json`. The active
package is preferred over legacy manually assembled bridge roots. A tampered
or incomplete active package makes `doctor`, `runtime verify`, and future
mapping installs fail with the manifest path and the affected artifact.

Every package activation retains the prior verified pointer in
`~/.ullage/runtimes/history.json`. Roll back without deleting packages:

```sh
bin/ullagectl runtime rollback --json
bin/ullagectl runtime rollback \
  --runtime-id macos-x86_64-lsteamclient --version VERSION --json
```

For a 64-bit title, stage the active package's canonical-name forwarder in its
initialized prefix. An existing GameHub/native prefix file is moved to a
same-directory `.ullage-original` backup before the atomic copy; it can be
restored with the matching command.

```sh
bin/ullagectl runtime stage-forwarder --prefix /path/to/prefix --json
bin/ullagectl runtime restore-forwarder --prefix /path/to/prefix --json
```

`runtime list` exposes both discovered host runtimes and installed package
provenance. A mapping records the package ID, version, manifest path, and
manifest digest; the bridge carries the same values into each session receipt.

## Versioned host-runtime option

The checked-in [`host-releases.json`](host-releases.json) locks the exact
GameHub Wine Proton 11.0 archive and the exact GPTK 3.0-3 source archive. It
does not contain a user prefix, native Steam, GameHub.app, or SandboxFS. On a
machine without GameHub, install the host option with:

```sh
bin/ullagectl runtime host-releases --json
bin/ullagectl runtime host-fetch --json
bin/ullagectl runtime host-verify --json
```

`host-fetch` verifies both archive size and SHA-256 before extracting. Wine is
downloaded from the tagged GitHub release using the original GameHub bytes;
GPTK is fetched from the locked original source URL. An exact local GPTK
archive can be supplied with `--gptk-archive PATH`. The installation is
atomic under `~/.ullage/host-runtimes`, and a verified pointer is written to
`host-runtimes/current.json` so `runtime list`, `doctor`, and install planning
can select it without reading GameHub's registry. The host runtime includes a
clean skeleton prefix at `wine/prefix`; Ullage still records per-game mappings
and must not publish or reuse private account-bearing prefixes.

## Renderer component overlays

Keep renderer components outside the repository and select them with a
per-AppID `--wine-root`. A runtime overlay must be an independent copy (an
APFS copy-on-write clone is suitable); do not use a hard-link tree as a
long-lived Wine root because Wine may write into it.

The tested DXMT 0.80 built-in layout for a 32-bit D3D11 title is:

```text
WINE_ROOT/lib/wine/i386-windows/{d3d10core,d3d11,dxgi,winemetal}.dll
WINE_ROOT/lib/wine/x86_64-unix/winemetal.so
PREFIX/drive_c/windows/syswow64/winemetal.dll
```

The [DXMT source](https://github.com/3Shain/dxmt) and its
[installation guide](https://github.com/3Shain/dxmt/wiki/DXMT-Installation-Guide-for-Geeks)
describe the matching built-in layout and loader rules. Do not add
`native,builtin` overrides for the built-in files unless the selected runtime
requires them.

This boundary is evidenced by Press Any Button (AppID 1448030) and POPGOES
Arcade (AppID 1986840): the normal GameHub runtime fell back to Wine Vulkan and
exited with `VK_ERROR_FEATURE_NOT_PRESENT`; both untouched depots rendered with
the DXMT i386 components above and retained the native Steam overlay. Press Any
Button also passed two native Steam Stop/relaunch cycles. This proves a
reusable runtime selection point, not universal DXMT compatibility. Ullage does
not vendor or download these components.
