# macOS runtime providers

Ullage has two independent runtime boundaries:

1. the small, versioned `lsteamclient` bridge package, which Ullage can fetch
   from GitHub; and
2. a host Wine/renderer/prefix provider, which supplies Windows API
   translation, graphics, and the initialized prefix.

The bridge is not a Wine distribution. A host provider is selected through the
same `runtime list` object, so the GUI does not need to understand GameHub's
private directory layout.

## Existing providers found on this Mac

The tested provider remains GameHub's x86_64 Wine Proton 11.0 runtime with
Apple GPTK 3.0-3. It has the strongest evidence: the clean-machine run reached
real Steam Play processes and rendered the known matrix controls, including
both 32-bit and 64-bit titles. Its virtual prefixes still contain user and
GameHub state and are never released by Ullage.

The machine also has `/Applications/Wine Staging.app`, installed through the
Homebrew `wine@staging` cask. It is a complete x86_64 Wine 11.10 distribution
with `bin/wine`, `wineserver`, `lib/wine`, Vulkan/MoltenVK support, and no
GPTK/D3DMetal component. Ullage exposes it as `wine-staging-app` so it is
visible as an option, but marks it incomplete for the current GPTK-required
bridge contract. It has not passed Ullage's native Steamworks launch matrix.
Homebrew currently reports the cask as deprecated because of Gatekeeper
behavior, so it should not silently become the default provider.

Other publicly available choices were checked for suitability:

* [Gcenx/macOS_Wine_builds](https://github.com/Gcenx/macOS_Wine_builds) is a
  maintained source/package path for ordinary Wine builds and is a useful
  baseline for the source-built provider.
* [Whisky](https://github.com/Whisky-App/Whisky) is archived and no longer
  actively maintained; it is not a new dependency for Ullage.
* [Kegworks](https://github.com/gxgl/Kegworks) is a Wineskin-style wrapper with
  multiple renderer choices, not the exact GameHub Wine/Proton + prefix
  contract.
* [CrossOver](https://www.codeweavers.com/crossover) is a commercial,
  user-supplied provider. Ullage should support it as an explicitly selected
  option only after a real Steamworks profile has been validated; it is not a
  release dependency.

## Exact GameHub release option

`runtime-macos-gamehub-2026-08-27-1` carries the original clean GameHub Wine
archive byte-for-byte and locks the original GPTK archive by URL, size, and
SHA-256. The installer places them under:

```text
~/.ullage/host-runtimes/macos-x86_64-gamehub-wine-proton-11/
  gamehub-wine-proton-11.0-gptk-3.0-3/
    wine/
      bin/
      lib/
      prefix/
    gptk/
```

The Wine archive includes a clean skeleton prefix. It does not include the
GameHub application, native Steam, GameHub's proprietary `libsandboxfs.dylib`,
or any per-game virtual prefix. Ullage's bridge package remains a separate
requirement and is recorded in the host manifest.

GPTK/D3DMetal is treated as an original-source/user-supplied component. The
release does not republish Apple's signed D3DMetal binary or GameHub's
SandboxFS library. A new machine can still install the exact stack without
installing GameHub:

```sh
bin/ullagectl runtime host-releases --json
bin/ullagectl runtime host-fetch --json
bin/ullagectl runtime verify --json
bin/ullagectl runtime host-verify --json
```

`host-fetch` obtains the Wine asset from the pinned GitHub release and the
GPTK archive from its locked original source URL. If that source is unavailable
or the user already has the exact archive, pass `--gptk-archive PATH`; the same
hash check applies. A GitHub-only, self-contained distribution is deliberately
not claimed for this provider.

## Source-built successor

The proper successor is a reproducible x86_64 Wine/Proton build whose source,
patches, compiler target, renderer choice, and clean prefix are all recorded.
The current source boundary is:

* Valve Wine `proton_11.0` at
  `dc26e61847081a1b5cb0733dc30feba6ee575482`;
* the matching two-patch macOS portability/lsteamclient series in
  [ullage-patches](https://github.com/xXJSONDeruloXx/ullage-patches) at
  `d2a5b75ed247f410cda746ca2cfe205e26f4f1ec`; and
* the existing Proton `dlls/lsteamclient` source, built for the same x86_64
  Wine tree rather than copied from an unrelated runtime.

The source build must produce a complete host runtime, not only the bridge:

```text
Wine/Proton binaries + lib/wine + clean prefix
        + lsteamclient Unix/PE outputs
        + one explicit renderer profile
        + a signed/hashable host manifest
```

Renderer profiles should remain separate experiments:

* WineD3D/MoltenVK is the ordinary open baseline and can be compared with the
  installed Wine Staging option.
* DXMT is a source-built D3D translation alternative for games that reject the
  baseline Vulkan path; it must remain a per-runtime/per-AppID overlay until
  the matrix proves broader compatibility.
* Apple GPTK/D3DMetal can remain an optional user-supplied overlay, but it is
  not an open-source build target and must not be presented as one.

The first source-built milestone is a clean, containerized build of Wine plus
the matching lsteamclient modules, followed by the same Peggle/Katamari
32-bit/64-bit control pair and a native Steam Play/Stop lifecycle check. A
full Proton distribution build is intentionally not required for that
milestone. The current host logs already identified the concrete build inputs:
Homebrew Bash 5, autoconf, modern bison, MinGW-w64, an amd64 SteamRT SDK
container on Apple Silicon, and enough temporary storage for the checkout and
build products. The source build remains an explicit successor track until it
passes that matrix with a clean prefix. The machine-readable source contract is
in [`runtime/source-build.json`](../runtime/source-build.json), so the eventual
builder can produce a host manifest without silently changing source or
renderer provenance.
