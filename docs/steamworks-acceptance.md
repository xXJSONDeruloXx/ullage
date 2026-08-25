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
| 3480 | Peggle Deluxe | P | P | I; overlay observed | not configured | P | Strongest 32-bit legacy control. |
| 584400 | Sonic Mania | P | P | I; native lsteamclient observed | P | P | Mixed-root Cloud mapping and a changed-file round trip were observed. |
| 848350 | Katamari Damacy REROLL | P | F (black surface) | I | P (2 files) | P | Good Cloud/transport test; renderer remains blocked. |
| 3784030 | RACCOON: Coin Pusher Roguelike | P | F (black surface) | I | P | P | Native Cloud changed-file upload round trip passed. |
| 1740930 | JellyCar Worlds | P | F (Unity/server failure) | I | P (22 files) | P | Cloud mapping works; game process does not reach a usable surface. |
| 304430 | INSIDE | P | F | I | no supported Windows root | P | Fresh Play-button run reached Wine; the post-fix secondary launch stayed alive 44s with a black full-screen surface and stopped cleanly via TERM. |
| 334940 | Yoku's Island Express | P | F | I | no supported Windows root | P | Fresh Play-button run reached Wine and exited 0 without a visible surface. |
| 356400 | Thumper | P | F | I | no supported Windows root | P | Default Win8 entry and the separate DX9 experiment both reached Wine; no surface. |
| 990630 | The Last Campfire | P | F | I | P (native mapping installed) | P | Fresh Play-button run reached Wine and exited 0 without a visible surface. |

The `P` lifecycle result means native Steam emitted an `App Running` transition,
the bridge logged `wine_exit`, and the client returned the AppID to its
installed state. It is not a claim that the game completed a meaningful play
session.

## Feature-level matrix

| Feature | Current evidence | Status |
| --- | --- | :---: |
| `SteamAPI_Init` | lsteamclient/native transport is present on proven runs, but no game-level API trace or controlled probe is committed | I |
| Identity (`ISteamUser::GetSteamID`) | Native Steam user/session context is retained; the game’s returned SteamID is not directly logged | I |
| Ownership/DRM | Entitled Windows depots install and native Steam tracks Play; no title has been certified against a DRM wrapper or ownership API result | I |
| Achievements/stats | Native library counters are observable, but no controlled unlock → `StoreStats` → relaunch test is complete | pending |
| DLC | No controlled `BIsDlcInstalled` plus DLC-content launch has been completed | pending |
| Overlay | Visible overlay attachment was observed with Geometry Wars, Peggle, and Sonic Mania renderer paths | P (title/renderer-specific) |
| Playtime | Native Steam updates local playtime and App Running/App stopped transitions after bridge runs | P (client telemetry) |
| Shutdown/relaunch | Clean `wine_exit=0` and signalled exits are recorded; repeat launch reaches the same boundary for the tested mappings | P (boundary) |

The next feature tests should use one known-visible title for the controlled
Steamworks probe and one Cloud title. The probe must record API-level results
without modifying the game depot; a diagnostic executable or a separately
staged Steamworks sample is preferable to instrumenting shipped game files.

## Cloud interpretation

For native Auto-Cloud, the relevant proof is the prefix path being the path
Steam itself watches. Steam documents that Auto-Cloud synchronizes before and
after sessions and that cross-platform behavior depends on root overrides; see
the [Steam Cloud documentation](https://partner.steamgames.com/doc/features/cloud).
The native Steam badge is therefore authoritative. A mapped prefix file and a
green badge are related outcomes, but one must not be synthesized by editing
`remotecache.vdf`.

## Depot and compatibility-tool boundary

Valve documents OS and architecture as depot mounting rules: a depot marked
for Windows is selected by a Windows client, while a separate Linux depot is
selected by a Linux client. See [Steam depots](https://partner.steamgames.com/doc/store/application/depots).
The Valve Proton manifest declares `from_oslist=windows` and
`to_oslist=linux`; see the [Proton compatibility-tool template](https://github.com/ValveSoftware/Proton/blob/proton_11.0/compatibilitytool.vdf.template).

Local appinfo inspection shows that `config/launch/*/config/oslist` filters
launch entries (for example, Windows and macOS alternatives in INSIDE), but it
does not document or demonstrate a per-AppID depot-platform override. The
current host still uses the global `@sSteamCmdForcePlatformType windows`
setting to obtain Windows content. Ullage must not silently replace that with
an appinfo launch-entry edit until a clean install experiment proves that the
content manifest, depot set, and verification state all remain Windows-only.

## Evidence paths

The durable code-side evidence is in `~/.ullage/logs/APPID-*.log` and Steam's
`logs/content_log.txt`; screenshots and temporary process inspection remain
host-local experiment artifacts. New rows should record the exact AppID,
runtime, prefix, launch entry, and whether the run was initiated by the native
Play button.
