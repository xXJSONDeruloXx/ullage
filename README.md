# Ullage

Ullage is the empty headspace of air and vapor between the surface of the wine
and the top of its container.

It is the gap between Steam and Wine on macOS.

Ullage is a small launch-boundary bridge for Windows Steam depots on native
macOS Steam. The normal Steam client remains the control plane: it downloads
the Windows files, owns the Play action, supplies the AppID/session context,
tracks the process, and starts its native overlay services. Ullage supplies
the missing execution boundary by launching the untouched Windows executable
through a prepared macOS Wine/GPTK runtime.

This is intentionally not a replacement Steam client, a Compatibility Manager,
or UI injection.

## The core idea

~~~text
native macOS Steam
        |
        | ordinary Play action
        v
local appcache launch mapping
        |
        | relative external launcher; depot stays untouched
        v
ullage-bridge
        |
        | allowlisted Steam environment and, by default, Steam IPC fds
        v
macOS Wine + GPTK/D3DMetal
        |
        | lsteamclient.dll + lsteamclient.so
        v
Windows PE game -> native Steam client/session/overlay
~~~

The install command changes only the local Steam appinfo cache entry for one
launch executable. The target PE is never renamed, wrapped, or overwritten.
Steam's content verification can therefore continue to operate on the actual
depot. The launcher lives outside the depot and is regenerated from recorded
state when needed.

The mapping is local and volatile: Steam updates may rewrite appinfo.vdf. Every
install makes a private appinfo backup, and the remove command restores the
recorded launch entry semantically. Generated launchers, mapping state,
backups, default prefixes, and logs live under `~/.ullage` by default (or the
`ULLAGE_STATE_DIR`/`--state-dir` override); the repository remains code and
runtime provenance.

## What is in the tree

* bin/ullage-install — validate a Windows PE and install an external Play
  mapping while Steam is stopped.
* bin/ullage-remove — restore the original launch entry and move generated
  state to recoverable backups.
* bin/ullage-mapping.py — read-only mapping health and conservative repair after
  Steam rewrites its local appinfo cache.
* bin/ullage-bridge — launch Wine with a clean, explicit environment and
  preserve native Steam transport by default.
* bin/ullage-reap — stop and reap only Wine helpers that still own the selected
  prefix; it never performs a global process-name kill.
* bin/ullage-appinfo.py — dependency-free editor for the single binary VDF
  launch record used by native macOS Steam.
* bin/ullage-path.py — tested path helper for Steam's install-root-relative
  external launcher entry.
* bin/ullage-cloud-path.py — deterministic mapping of Windows Steam Cloud
  roots into the selected Wine prefix for native Cloud mapping.
* bin/ullage-cloud-native.py — local appinfo root overrides and guarded
  MacAppSupport symlinks so native Steam owns Cloud transfer and badge state.
* bin/ullage-fd-exec — universal descriptor-boundary helper, built from
  src/ullage-fd-exec.c.
* tools/ullage-steamworks-probe.c — optional MinGW diagnostic for direct
  SteamAPI initialization, identity, ownership, stats, DLC, overlay, and
  shutdown checks without modifying a shipped depot.
* runtime/README.md — runtime and lsteamclient contract. The large third-party
  binaries are supplied by the host rather than committed here.

## Prerequisites

1. Native macOS Steam must be configured to retain Windows depots. The
   experimental native-client setting is:

   ~~~text
   @sSteamCmdForcePlatformType windows
   ~~~

   Ullage does not edit this setting or manage depot selection.
2. A prepared Wine prefix with system.reg. Use one prefix per AppID while the
   lifecycle/reaper work is still experimental.
3. A Wine runtime, GPTK/D3DMetal runtime, and compatible lsteamclient artifacts
   matching runtime/README.md.
4. Native Steam's Steam.AppBundle/Steam/Contents/MacOS/steamclient.dylib.

For 64-bit games, build and stage the small `steamclient64.dll` forwarder
described in [runtime/README.md](runtime/README.md). Ullage checks the staged
copy before launch; it does not modify the prefix in the launch hot path.

Build and syntax-check the only native helper:

~~~sh
cd "$HOME/Developer/ullage"
make
make check
~~~

## Install a mapping

Steam must be fully quit while appcache/appinfo.vdf is edited. The command
requires explicit runtime roots so a different Wine provider or GPTK build can
be used without changing the repository:

~~~sh
REPO="$HOME/Developer/ullage"
STEAM_ROOT="$HOME/Library/Application Support/Steam"

"$REPO/bin/ullage-install" \
  --appid APPID \
  --target "$STEAM_ROOT/steamapps/common/Title/Game.exe" \
  --install-dir "$STEAM_ROOT/steamapps/common/Title" \
  --prefix "$HOME/Library/Application Support/ullage/prefixes/APPID" \
  --wine-root "/path/to/wine" \
  --gptk-root "/path/to/gptk" \
  --bridge-root "/path/to/lsteamclient" \
  --steam-root "$STEAM_ROOT" \
  --cloud-native \
  --log "$HOME/Library/Logs/ullage/APPID.log"
~~~

Add --arch win32 or --arch win64 when automatic PE detection is not enough.
Use --wine-dllpath with a colon-separated path when an alternate Wine/D3D
runtime must take precedence over the default GPTK DLL directories; leaving it
unset preserves the standard runtime ordering.
Add --legacy-steam only for older titles whose prepared prefix contains the
legacy Steam DLL set. Transport preservation is the default; use
--clean-steam-transport only as a title-specific fallback.
If Steam's cached launch entry names a wrapper or stale executable instead of
the target PE, pass its numeric key with `--launch-entry KEY`; the installer
otherwise matches the target filename.

Restart native Steam after installation and press the ordinary Play button.
The generated launcher receives Steam's game arguments and the bridge waits
for the exact Wine launcher to exit, then waits for the prefix's Wine session
to become idle before reaping prefix-owned helper processes. This keeps a slow
game startup from being killed by an early `wineserver -w` return and gives
Steam one supervised launch boundary even when Wine's `start.exe` launcher
outlives the Windows process.

The macOS client currently records an external launcher and enters `Stopping`
without signalling that launcher. By default the bridge watches the native
Steam `logs/content_log.txt` from its launch-time offset for the exact AppID's
`Terminating` state, then routes that request through the same signal and
prefix-scoped cleanup path. This keeps the ordinary Steam Stop button useful
without injecting into Steam's UI; `STEAM_STOP_WATCH=0` disables the adapter for
diagnostics only.

## Check or repair a mapping

Steam can regenerate `appcache/appinfo.vdf` during a client update or metadata
refresh. Inspect a mapping while Steam is running or stopped:

~~~sh
"$HOME/Developer/ullage/bin/ullage-mapping.py" status \
  --appid APPID \
  --steam-root "$HOME/Library/Application Support/Steam"
~~~

`status=healthy` means the recorded launch entry, generated config, and
launcher agree. `stale` means Steam restored the recorded native executable;
`foreign` means some other local change owns the entry; `broken` means the
entry still points at Ullage but generated state is incomplete. Status is
read-only and returns nonzero for anything that is not healthy.

After fully quitting Steam, a stale mapping can be reapplied atomically:

~~~sh
"$HOME/Developer/ullage/bin/ullage-mapping.py" repair \
  --appid APPID \
  --steam-root "$HOME/Library/Application Support/Steam"
~~~

Repair writes a private appinfo backup under `~/.ullage/backups/appinfo`, uses
the recorded entry as an optimistic concurrency check, and refuses to
overwrite a foreign mapping unless `--force` is explicit. It does not recreate
missing runtime state; reinstall or restore that state first.

For a Windows depot's Auto-Cloud files, `--cloud-native` is the supported path.
It edits the local UFS metadata while Steam is stopped, adding an
`os=Windows` `useinstead=MacAppSupport` override that matches the forced depot
platform. It then creates a guarded symlink such as:

~~~text
~/Library/Application Support/Ullage/848350
    -> <Wine prefix>/drive_c/users/steamuser/AppData/Local
~~~

The native mapper covers these Windows/all-platform roots:

| UFS root | Wine target |
| --- | --- |
| `WindowsHome` | the Wine user's home directory |
| `WinMyDocuments` | `Documents` |
| `WinAppDataLocal` | `AppData/Local` |
| `WinAppDataLocalLow` | `AppData/LocalLow` |
| `WinAppDataRoaming` | `AppData/Roaming` |
| `WinSavedGames` | `Saved Games` |
| `WinProgramData` | prefix `ProgramData` |
| `SteamCloudDocuments` | `Documents/Steam Cloud/<Steam login>/<game folder>` |
| `gameinstall` | the Steam install directory |

`SteamCloudDocuments` uses the Windows path convention even though its root is
available on all platforms. Ullage derives the Steam login name from
`config/loginusers.vdf`; `--cloud-steam-account-name` is available when the
client has multiple login records. `gameinstall` and
`SteamCloudDocuments` use the install directory already supplied to
`ullage-install` via `--install-dir`.

Native Steam consequently watches, downloads, uploads, hashes, and records the
real prefix files itself. The generated mapping is recorded in
`~/.ullage/config/games/APPID.cloud.json`; `ullage-remove` restores it and only
removes symlinks that still point at the recorded prefix target. Steam may
rewrite its local appinfo cache during a metadata refresh, so the install
operation is intentionally repeatable rather than pretending this is a server
metadata change.

If Steam already has a file in its local `userdata/<account>/<appid>/remote`
cache but the prefix is missing it, install performs a one-time size/SHA-1
verified local seed when the file matches the current UFS rule. This handles
stale local root IDs without opening a browser or making a network request; it
never overwrites an existing prefix file. Native Steam owns all subsequent
Cloud transfer and conflict behavior.

This native path is the only Ullage Cloud transport. Native Steam watches,
downloads, uploads, hashes, and records the real prefix files itself; Ullage
does not provide a browser, token, or per-file transfer fallback. The default
`--cloud-wine-user auto` reads the prefix's `user.reg` and maps files into the
Windows user that the game actually runs as; pass an explicit name only for a
deliberately nonstandard prefix.

The badge is now part of the native path rather than a UI fiction. Once the
override points at the prefix, Steam's own Auto-Cloud resolver updates
`remotecache.vdf` and the normal macOS client displays the ordinary current
Cloud state. This is proven locally for Katamari Damacy REROLL, JellyCar
Worlds, RACCOON, Sonic Mania, and FAR: Lone Sails. It is not yet a universal
claim: titles with different UFS roots, path transforms, or a Steam metadata
refresh still need acceptance testing.

The external token, CEF/CDP, and pre/post lifecycle fallback paths were
removed deliberately. Mac/Linux roots that appear as alternatives in a
cross-platform UFS record are not Windows game paths and are ignored. Ullage
maps every recognized Windows/all-platform root in a mixed record, fails on an
unknown Windows-specific root instead of guessing, and fails when a requested
native mapping has no recognized root. The install output and recorded state
list exactly which roots were mapped.
Older generated configs may still contain the removed `CLOUD_*` assignments;
the bridge ignores those inert values, while external scripts using the
removed command-line options must migrate to `--cloud-native`.

The supported-root evidence ledger and remaining native-save TODOs are in
[`docs/native-saves.md`](docs/native-saves.md). It distinguishes unit-tested
root coverage from live title acceptance and does not treat native Steam's
badge as proof that every game writes the expected save.

A fresh Katamari setup was validated from a clean appinfo baseline with a new
state directory: native Steam displayed “Your Steam Cloud files are
synchronized for this app,” its local `remotecache.vdf` contained both save
records, and native Play/Stop completed through the PR branch without any
browser or token-based transfer.

Additional fresh checks cover different depot and runtime shapes. Sonic Mania
was mapped from a new state directory as a 32-bit PE executable with both its
`WinAppDataLocal` and `SteamCloudDocuments` roots. Native Steam created
`steam_autocloud.vdf` below the mapped prefix-side
`Documents/Steam Cloud/<Steam login>/Sonic Mania/SavesDir` path, and the Wine session
exited cleanly with no remaining processes. FAR: Lone Sails was downloaded
through Steam into a previously uninstalled library entry, then mapped as a
64-bit Unity Windows depot with a nested executable and
`WinAppDataLocalLow` Cloud root. Unity initialized SteamManager, Steam showed
synchronized after the prefix files appeared, and native Stop reaped the Wine
session cleanly. A second real run mapped Thumper's `gameinstall` root and
Steam watched its three existing `savedata` files through the install-directory
symlink. The FAR and Thumper installs remain on disk after the reversible tests.

For games whose Windows executable is nested below the install root (for
example, `windows/Game.exe`), set `--install-dir` to the Steam install
directory. `--game-dir` remains the Wine working directory; the tested path
helper computes the patched launch entry from `--install-dir`.

To restore the native launch entry, quit Steam and run:

~~~sh
"$HOME/Developer/ullage/bin/ullage-remove" \
  --appid APPID \
  --steam-root "$HOME/Library/Application Support/Steam"
~~~

## What the design preserves

* Steam's native AppID and user/session context.
* Native Steam loader and overlay environment.
* Inherited Steam IPC descriptors when transport preservation is enabled.
* Steam virtual-gamepad metadata, including Proton's
  `SteamVirtualGamepadInfo_Proton` fallback.
* Native Steam's process add/update/remove lifecycle.
* Native Steam's Stop action through the AppID-scoped termination watcher.
* The original Windows depot files and their verification surface.
* A bounded, prefix-scoped cleanup path for Wine infrastructure processes.

## Current boundary

The launch architecture is proven across both 32-bit legacy and 64-bit Unity
Windows titles in the local experiment, including native Steam Stop cleanup on
Peggle, Katamari, Sonic Mania, and FAR: Lone Sails. Visible rendering and
native overlay attachment are proven on some renderer paths. That is evidence
for the boundary, not a universal compatibility claim.

Steam Cloud root resolution is unit-tested across all supported Windows and
all-platform roots, and a reversible changed-file upload round trip is proven
through the native path for RACCOIN. Sonic's expanded real-game run also
proved the `SteamCloudDocuments` mapping by observing Steam's generated file
inside the prefix. Steam's virtual-gamepad handoff is live-verified, but
physical controller behavior is not yet tested on this host.
Full DRM certification,
conflict policy, and all Unity/D3DMetal window paths still need per-title
acceptance tests. The bridge records Steamworks transport and lifecycle
evidence, but it does not claim that every game renderer, DRM scheme, or cloud
implementation works.

The optional direct Steamworks probe passes initialization, identity,
ownership, stats, DLC enumeration, and shutdown for Katamari's 32-bit and
64-bit API DLLs when the canonical-name forwarder is staged. The forwarder is
kept outside this repository with the other Wine/Proton runtime work, and the
bridge checks its prefix copy before launch.

The next work belongs above this small core: runtime discovery, renderer
profiles, cloud verification, arm64-native Wine, and recovery when Steam
rewrites its local launch cache.

Upstream-sensitive Wine/Proton portability work is maintained separately in
[ullage-patches](https://github.com/xXJSONDeruloXx/ullage-patches), with pinned
source provenance and reproducible patch checks. This repository intentionally
remains the small Steam launch bridge rather than becoming a dependency fork.
