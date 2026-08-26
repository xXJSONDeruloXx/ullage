# Runtime contract

Ullage deliberately does not vendor Wine, GPTK/D3DMetal, native Steam, or
Proton/Wine-derived lsteamclient binaries. Those components have their own
release cadence and licensing. Point the installer at the runtime selected by
the host setup.

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

This boundary is evidenced by Press Any Button (AppID 1448030): the normal
GameHub runtime fell back to Wine Vulkan and exited with
`VK_ERROR_FEATURE_NOT_PRESENT`; the same untouched depot rendered with the
DXMT i386 components above, retained the native Steam overlay, and passed two
native Steam Stop/relaunch cycles. This proves a reusable runtime selection
point, not universal DXMT compatibility. Ullage does not vendor or download
these components.
