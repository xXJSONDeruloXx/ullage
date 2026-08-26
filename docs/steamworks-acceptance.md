# Steamworks and launch acceptance

This is the current evidence ledger for the native-Steam launch boundary. A
bridge log proves that Ullage started Wine and preserved the Steam launch
transport; it does not by itself prove that a game called `SteamAPI_Init`,
obtained a valid identity, or exercised every Steamworks interface.

## Acceptance levels

* **Boundary** — native Steam marked the AppID running, the launcher reached
  `ullage-bridge`, and the bridge recorded a clean or signalled exit.
* **Renderer** — a fresh screenshot showed the Windows game surface, not only
  the Steam library page.
* **Steamworks transport** — the run retained the native Steam launch
  environment and the expected lsteamclient artifacts; this is indirect API
  evidence, not an API trace.
* **Feature** — the feature was deliberately exercised and its native Steam
  result was observed. Do not infer this level from a green Play button.
* **Stop** — the native Steam Stop action produced an AppID-scoped termination
  event, the bridge exited, and no selected-prefix Wine processes remained.

The direct Steamworks lifecycle contract is: initialize successfully before
using interfaces, dispatch callbacks regularly, and shut down during process
exit when possible. See the [Steamworks API overview](https://partner.steamgames.com/doc/sdk/api)
and [`steam_api.h`](https://partner.steamgames.com/doc/api/steam_api).

## Real-game matrix

The rows below are from the macOS host experiment, using the ordinary native
Steam Play button unless noted. `P` means proven at that level, `I` means
indirect evidence only, and `F` means the run reached the boundary but failed
the acceptance criterion.

| AppID | Title | Depot/launch boundary | Renderer | Steamworks transport | Cloud | Lifecycle | Current note |
| ---: | --- | --- | :---: | :---: | :---: | :---: | --- |
| 8400 | Geometry Wars: Retro Evolved | P | P historically; latest repeats F | I | not configured | P | 32-bit path and overlay were visible in an earlier run; repeatability is an open renderer issue. |
| 3480 | Peggle Deluxe | P | P | I; overlay observed | not configured | P | Strongest 32-bit legacy control; native Stop cleanup passed. |
| 584400 | Sonic Mania | P | P | I; native lsteamclient observed | P (`WinAppDataLocal` + `SteamCloudDocuments`) | P | Fresh mixed-root mapping caused Steam to create `steam_autocloud.vdf` under the Wine prefix's Windows `Documents/Steam Cloud` path. |
| 848350 | Katamari Damacy REROLL | P | P (forwarder staged) | P (x64 probe + native Play) | P (2 files) | P | Canonical-name `steamclient64.dll` forwarder removed the shared x64 SteamAPI stall; repeated Play/confirmed Stop/relaunch on 2026-08-25 returned cleanly to Play. |
| 3784030 | RACCOON: Coin Pusher Roguelike | P | F (black surface) | I | P | P | Native Cloud changed-file upload round trip passed. |
| 1740930 | JellyCar Worlds | P | F (Unity/server failure) | I | P (22 files) | P | Cloud mapping works; game process does not reach a usable surface. |
| 304430 | INSIDE | P | F | I | no supported Windows root | P | Fresh Play-button run reached Wine; the post-fix secondary launch stayed alive 44s with a black full-screen surface and stopped cleanly via TERM. |
| 334940 | Yoku's Island Express | P | F | I | no supported Windows root | P | Fresh Play-button run reached Wine and exited 0 without a visible surface. |
| 356400 | Thumper | P | F | I | P (`gameinstall`) | P | Fresh Win8 run watched all three existing `savedata` files through the mapped Steam install directory; no surface. |
| 990630 | The Last Campfire | P | F | I | P (native mapping installed) | P | Fresh Play-button run reached Wine and exited 0 without a visible surface. |
| 1880620 | Once Upon A KATAMARI | P | F | I | I (mapping installed; no save round trip) | P | Native Play reached Running twice, but Wine reported `Application load error 3:0000065432` before the Unity game assembly or game Steam API DLL loaded. A separate staged API probe passed initialization, identity, ownership, and DLC enumeration; that does not certify the shipped game session. |

The `P` lifecycle result means native Steam emitted an `App Running` transition,
the bridge logged `wine_exit`, and the client returned the AppID to its
installed state. It is not a claim that the game completed a meaningful play
session.

## Feature-level matrix

| Feature | Current evidence | Status |
| --- | --- | :---: |
| `SteamAPI_Init` | Katamari's 32-bit and 64-bit API DLLs both initialized; the x64 run required the canonical-name forwarder staged at the prefix Steam path | P (win32 + win64) |
| Identity (`ISteamUser::GetSteamID`) | Direct probes returned a logged-on, nonzero SteamID on both architectures | P (win32 + win64 probe) |
| Ownership/DRM | Direct probes returned subscribed and subscribed-to-AppID; a DRM-wrapper title is not certified | P (win32 + win64 probe); pending (DRM wrapper) |
| Achievements/stats | Katamari's x64 probe requested current stats and enumerated 21 achievements, including state for the first entry; no controlled unlock/store/relaunch test is complete | P (read-only); pending (write path) |
| DLC | Katamari's x64 probe called DLC enumeration and returned count 0; no DLC-content launch has been completed | P (enumeration); pending (content) |
| Overlay | Direct probe reported `IsOverlayEnabled=0` for Katamari; visible overlay attachment was observed with Geometry Wars, Peggle, and Sonic Mania renderer paths | P (title/renderer-specific) |
| Playtime | Native Steam updates local playtime and App Running/App stopped transitions after bridge runs | P (client telemetry) |
| Steam Stop | Native Steam emitted `App Running,Terminating`; the bridge routed it through its signal trap, reaped the selected prefix, and returned Peggle and Katamari to Play with no Wine/helper processes remaining | P |
| Shutdown/relaunch | Direct x64 probe reached `SteamAPI_Shutdown`; native Play/Stop runs also returned Katamari to Play with no selected-prefix Wine processes remaining | P (win32 + win64/boundary) |

The next feature tests should use one known-visible title for the controlled
Steamworks probe and one Cloud title. The probe must record API-level results
without modifying the game depot; a diagnostic executable or a separately
staged Steamworks sample is preferable to instrumenting shipped game files.

## Direct Steamworks probe

`tools/ullage-steamworks-probe.c` is an optional MinGW-built diagnostic. It
loads the matching `steam_api.dll` or `steam_api64.dll` beside the probe and
uses the game's flat exports, so it does not replace the game's Steamworks
library or alter the depot. `SteamAPI_Init` is bounded by a ten-second watchdog;
exit 124 means the runtime is stuck in initialization rather than that the
probe silently passed.

Compile both architectures when the host has MinGW:

~~~sh
x86_64-w64-mingw32-gcc -O2 -Wall -Wextra -Werror -o /tmp/ullage-probe64.exe tools/ullage-steamworks-probe.c
i686-w64-mingw32-gcc -O2 -Wall -Wextra -Werror -o /tmp/ullage-probe32.exe tools/ullage-steamworks-probe.c
~~~

On the current Katamari depot, the 32-bit and 64-bit probes returned
`SteamAPI_Init`, a logged-on identity, matching AppID, subscription/ownership,
DLC count, achievement enumeration, and `SteamAPI_Shutdown`. The x64 run uses
the small canonical-name forwarder described in `runtime/README.md`; the
untouched lsteamclient image still stalls when loaded directly as
`steamclient64.dll`. The forwarder is a runtime prerequisite, not a game or
Steam-client modification.

The native Steam Play run then rendered Katamari through the same prefix, and
the native Stop confirmation produced an AppID-scoped `Terminating` event;
the bridge exited with `wine_exit=143 signal_received=1`, and process
inspection found no Katamari, Wine server, or prefix-owned helper remaining.

## Stop and cleanup boundary

The native macOS client tracks the external launcher and its Wine descendants,
but its Stop action does not signal the generated shell launcher in this
configuration. Ullage therefore watches only new lines in native Steam's
`logs/content_log.txt` for the active AppID's `Terminating` state. It then sends
`TERM` through the ordinary bridge supervisor, waits for the exact Wine child,
and runs the existing prefix-scoped reaper. This is a small Steam-specific
adapter at the boundary, not UI injection or a global process-name kill.

The behavior was exercised through the native Play/Stop UI with Peggle and
Katamari: both exited with `wine_exit=143 signal_received=1`, Steam returned to
the normal Play state, and process inspection found no game, Wine server, or
prefix-owned helper left behind.

## Cloud interpretation

The focused native-save evidence ledger, including the supported root table
and remaining TODOs, is in [`native-saves.md`](native-saves.md).

For native Auto-Cloud, the relevant proof is the prefix path being the path
Steam itself watches. Steam documents that Auto-Cloud synchronizes before and
after sessions and that cross-platform behavior depends on root overrides; see
the [Steam Cloud documentation](https://partner.steamgames.com/doc/features/cloud).
The native Steam badge is therefore authoritative. A mapped prefix file and a
green badge are related outcomes, but one must not be synthesized by editing
`remotecache.vdf`.

The native mapper currently handles `WindowsHome`, the four Windows AppData/
Documents roots, `WinProgramData`, `SteamCloudDocuments`, and `gameinstall`.
Mac/Linux roots in a mixed UFS record are platform alternatives and are not
mapped into the forced Windows prefix. An unknown Windows-prefixed root fails
setup rather than being guessed. `SteamCloudDocuments` uses the Windows
`Documents/Steam Cloud/<login>/<game>` layout; its login name comes from
Steam's `loginusers.vdf` unless explicitly supplied.

## Depot and compatibility-tool boundary

The detailed per-AppID investigation is in
[`platform-selection.md`](platform-selection.md). In brief, launch `oslist`
and depot `oslist` are separate, and a clean Peggle install showed that a
native `compat.vdf` platform override does not select the Windows depot. A
follow-up no-op compatibility-tool probe showed that native macOS Steam logs
global and per-AppID `CompatToolMapping` entries but does not dispatch the
tool. The host therefore retains the global
`@sSteamCmdForcePlatformType windows` setting and the offline appinfo launch
mapping. See [`compatibility-tool-research.md`](compatibility-tool-research.md)
for the exact negative result and reconsideration gate.

## Evidence paths

The durable code-side evidence is in `~/.ullage/logs/APPID-*.log` and Steam's
`logs/content_log.txt`; screenshots and temporary process inspection remain
host-local experiment artifacts. New rows should record the exact AppID,
runtime, prefix, launch entry, and whether the run was initiated by the native
Play button.
