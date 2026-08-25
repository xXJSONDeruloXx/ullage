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

The lsteamclient pair is the Wine-side Steam transport built from a compatible
Proton/Wine source tree. On Apple Silicon, the currently tested third-party
Wine runtime is x86_64 under Rosetta; an arm64-native Wine runtime is a future
target, not an assumption made by this repository.

The native Steam client remains the source of steamclient.dylib, loader
environment, IPC descriptors, user/session state, and overlay services. Ullage
only passes those through the Wine launch boundary.
