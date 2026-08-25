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
recorded launch entry semantically. Keep the generated state under the repo
directory out of version control.

## What is in the tree

* bin/ullage-install — validate a Windows PE and install an external Play
  mapping while Steam is stopped.
* bin/ullage-remove — restore the original launch entry and move generated
  state to recoverable backups.
* bin/ullage-bridge — launch Wine with a clean, explicit environment and
  preserve native Steam transport by default.
* bin/ullage-reap — stop and reap only Wine helpers that still own the selected
  prefix; it never performs a global process-name kill.
* bin/ullage-appinfo.py — dependency-free editor for the single binary VDF
  launch record used by native macOS Steam.
* bin/ullage-cloud-path.py — deterministic mapping of Windows Steam Cloud
  roots into the selected Wine prefix; transport is intentionally separate.
* bin/ullage-cloud-sync.py — read-only Steam Cloud enumeration and optional
  prefix download using `ULLAGE_STEAM_ACCESS_TOKEN`; uploads remain gated.
* bin/ullage-cloud-cdp.mjs — optional native Steam CEF/CDP Cloud metadata
  reader using the logged-in browser session without persisting credentials.
* bin/ullage-fd-exec — universal descriptor-boundary helper, built from
  src/ullage-fd-exec.c.
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
  --prefix "$HOME/Library/Application Support/ullage/prefixes/APPID" \
  --wine-root "/path/to/wine" \
  --gptk-root "/path/to/gptk" \
  --bridge-root "/path/to/lsteamclient" \
  --steam-root "$STEAM_ROOT" \
  --log "$HOME/Library/Logs/ullage/APPID.log"
~~~

Add --arch win32 or --arch win64 when automatic PE detection is not enough.
Add --legacy-steam only for older titles whose prepared prefix contains the
legacy Steam DLL set. Transport preservation is the default; use
--clean-steam-transport only as a title-specific fallback.

Restart native Steam after installation and press the ordinary Play button.
The generated launcher receives Steam's game arguments and the bridge waits
for Wine to exit before reaping prefix-owned helper processes, so Steam sees
one supervised launch boundary.

Cloud lifecycle hooks are available without changing the Play mapping. Set an
external command with `--cloud-sync-command`; Ullage runs it once with
`ULLAGE_CLOUD_PHASE=pre` before Wine and once with `post` after Wine/reaping.
The command also receives `ULLAGE_APPID`, `ULLAGE_PREFIX`, `ULLAGE_APPINFO`,
`ULLAGE_STEAM_ROOT`, `ULLAGE_STEAM3_ACCOUNT_ID`, and `ULLAGE_WINE_USER`. This
keeps credentials out of generated appinfo and lets one reusable hook invoke
`bin/ullage-cloud-hook`, which selects `--download` before launch and
`--upload` after exit. Upload is explicit local-wins behavior and should not be
enabled until the title's conflict policy is understood.

For a Steam client started with `-cef-enable-debugging`, add `--cloud-cdp` to
use the native authenticated CEF session for pre-launch downloads. CDP mode is
read/download-only; post-exit upload is skipped rather than falsely reported.

The Steam Cloud badge has an important boundary. Native Steam is the authority
for the badge, and it only becomes `Up to date` when that client can resolve the
game's published Auto-Cloud root on macOS. A Windows-only game's
`WinAppData*` root is not repaired by changing local `appinfo.vdf`,
`remotecache.vdf`, or `localconfig.vdf`; the client re-evaluates and overwrites
those attempts. Ullage therefore keeps prefix Cloud transfer and native Steam
badge state separate: the hook can verify/download the prefix files, but it
does not fake Steam's state. A true native badge for such a title needs a
published macOS root override or a maintained native Steam Cloud resolver
patch.

For games whose Windows executable is nested below the install root (for
example, `windows/Game.exe`), set `--game-dir` to the Steam install directory,
not the nested executable directory. Steam resolves the patched launch entry
relative to that install root.

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
* Native Steam's process add/update/remove lifecycle.
* The original Windows depot files and their verification surface.
* A bounded, prefix-scoped cleanup path for Wine infrastructure processes.

## Current boundary

The launch architecture is proven across both 32-bit legacy and 64-bit Unity
Windows titles in the local experiment, including visible rendering and native
overlay attachment on some renderer paths. That is evidence for the boundary,
not a universal compatibility claim.

Full DRM certification, Steam Cloud synchronization, controller coverage, and
all Unity/D3DMetal window paths still need per-title acceptance tests. The
bridge records Steamworks transport and lifecycle evidence, but it does not
claim that every game renderer, DRM scheme, or cloud implementation works.

The next work belongs above this small core: runtime discovery, renderer
profiles, cloud verification, arm64-native Wine, and recovery when Steam
rewrites its local launch cache.

Upstream-sensitive Wine/Proton portability work is maintained separately in
[ullage-patches](https://github.com/xXJSONDeruloXx/ullage-patches), with pinned
source provenance and reproducible patch checks. This repository intentionally
remains the small Steam launch bridge rather than becoming a dependency fork.
