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
| 3590 | Plants vs. Zombies: Game of the Year | P | P | P; x86 lsteamclient and `gameoverlayui` observed | not configured | I | Fresh 48 MB Windows depot rendered its title screen through the public package. Fullscreen occlusion hid the Steam Helper Stop control; quitting Steam exercised the generic client-exit fallback and cleaned the prefix, but no AppID-scoped Stop event was claimed. |
| 6100 | Eets | P | P | I; x86 bridge injection logged, no `gameoverlayui` process | I (`gameinstall` mapping; Steam AutoCloud disabled, zero watched files) | P | Fresh 143 MB Windows depot rendered the main menu. Native Stop and uninstall/removal passed; no shipped-game API or Cloud transfer claim is made. |
| 584400 | Sonic Mania | P | P | I; native lsteamclient observed | P (`WinAppDataLocal` + `SteamCloudDocuments`) | P | Fresh mixed-root mapping caused Steam to create `steam_autocloud.vdf` under the Wine prefix's Windows `Documents/Steam Cloud` path. |
| 848350 | Katamari Damacy REROLL | P | P (forwarder staged) | P (x64 probe + native Play) | P (2 files) | P | Canonical-name `steamclient64.dll` forwarder removed the shared x64 SteamAPI stall; repeated Play/confirmed Stop/relaunch on 2026-08-25 returned cleanly to Play. |
| 3784030 | RACCOON: Coin Pusher Roguelike | P | F (black surface) | I | P | P | Native Cloud changed-file upload round trip passed. |
| 1740930 | JellyCar Worlds | P | F (Unity/server failure) | I | P (22 files) | P | Cloud mapping works; game process does not reach a usable surface. |
| 304430 | INSIDE | P | F | I | no supported Windows root | P | Fresh Play-button run reached Wine; the post-fix secondary launch stayed alive 44s with a black full-screen surface and stopped cleanly via TERM. |
| 334940 | Yoku's Island Express | P | F | I | no supported Windows root | P | Fresh Play-button run reached Wine and exited 0 without a visible surface. |
| 356400 | Thumper | P | F | I | P (`gameinstall`) | P | Fresh multi-option retest redirected all four installed Windows entries; default and DX9 reached their selected executables, the Steam VR option preserved `-openvr`, and native Stop returned each tested path cleanly. Wine's `Application load error 3:0000065432` remained a runtime/title renderer boundary. |
| 990630 | The Last Campfire | P | F | I | P (native mapping installed) | P | Fresh Play-button run reached Wine and exited 0 without a visible surface. |
| 1880620 | Once Upon A KATAMARI | P | F | I | I (mapping installed; no save round trip) | P | Native Play reached Running twice, but Wine reported `Application load error 3:0000065432` before the Unity game assembly or game Steam API DLL loaded. A separate staged API probe passed initialization, identity, ownership, and DLC enumeration; that does not certify the shipped game session. |
| 858710 | Gravity Circuit | P | P | I | I (mapping and checked badge; no save round trip) | P | Fresh nested x64 depot rendered its language-selection surface with the native overlay attached. Two native Play/Stop cycles returned to Play; the shipped game was not instrumented for API-level feature calls. |
| 4182710 | Dustin Sunset | P | P | I | not configured | P | Fresh flat x64 Unity depot rendered the title surface with `gameoverlayui` attached. Two native Play/confirmed-Stop cycles returned to Play; no shipped-game Steamworks feature calls or Cloud roots were exercised. |
| 403400 | ARCADE GAME SERIES: DIG DUG | P | P | I | I (mapping and checked badge; no save round trip) | P | Fresh Windows-only x64 Unity depot rendered its auto-save caution surface with `gameoverlayui` attached. Native Stop returned to Play and Steam uninstall plus Ullage removal completed cleanly; the shipped game's Steamworks feature calls were not instrumented. |
| 1743850 | HYPER DEMON | P | F | I | not configured | P | Native Play reached Running, but GLFW/OpenGL context creation failed before a usable game surface. No shipped-game Steamworks calls or Cloud roots were exercised; natural exit cleanup passed and native Stop was not needed. |
| 292280 | SPY Fox in: Cheese Chase | P | P | I | I (`gameinstall` mapping; no save round trip) | P | Fresh 32-bit ScummVM Windows depot. Native Play reached the rendered title scene with `gameoverlayui` attached; two native Stop cycles returned to Play and left no selected-prefix processes. The native mapper installed and restored the `gameinstall` root, but no Cloud transfer or shipped-game API feature was deliberately exercised. |
| 1086010 | 198X | P | P | I; x64 lsteamclient and `gameoverlayui` observed | not supported | P | Fresh 500.66 MB x64 depot. The ordinary mapping path rendered the 198X menu twice; explicit `--cloud-native` planning correctly refused the title because appinfo has no supported Windows Cloud root. Both native Stop cycles returned to Play with clean prefixes, and Steam uninstall plus Ullage removal completed cleanly. No shipped-game API feature or visible overlay interaction is claimed. |
| 2932930 | 100 Korea Cats | P | P | I; x64 lsteamclient and `gameoverlayui` observed | not supported | P | Fresh 290.88 MB x64 depot. The ordinary mapping path rendered the title menu; appinfo has no supported Windows Cloud root. Native Stop and Steam uninstall plus Ullage removal completed cleanly. No shipped-game API feature or visible overlay interaction is claimed. |
| 1037190 | Shipped | P | P | I; x64 Steam loader, overlay renderer, and eventual `gameoverlayui` observed | not supported | P | Fresh 250.38 MB x64 depot. The initial game-window capture was black during Unity startup; a bounded wait reached the rendered Controls screen. Native Stop and cleanup passed. No shipped-game API feature or visible overlay interaction is claimed. |
| 1003830 | Cold Silence | P | F | I; x64 lsteamclient, Steam loader, and overlay renderer observed | I (`WinAppDataLocal` mapping; zero watched files) | P | Fresh 52.93 MB x64 GameMaker depot. Native Play reached the title's `CheckMultisampleQualityLevels` error (`HRESULT 0x80070057`) before a usable surface. Native Stop returned to Play with a clean prefix; Steam uninstall plus Ullage removal passed. No shipped-game API feature or visible overlay interaction is claimed. |
| 861320 | Beyond Minimalism | P | P | I; x86 lsteamclient, Steam loader, overlay renderer, and `gameoverlayui` observed | not supported | P | Fresh 51.01 MB win32 depot. A scoped in-prefix `BM_CLICK` probe advanced the title's configuration dialog, after which a window-specific capture showed the rendered title screen. Native Stop, Steam uninstall, and Ullage removal passed. No shipped-game API feature or visible overlay interaction is claimed. |
| 322190 | SteamWorld Heist | P | P | I | I (`MacAppSupport` observed; no Windows mapping or save round trip) | P | Fresh 32-bit sprite/OpenAL Windows depot. Native Play reached the interactive menu with `gameoverlayui` attached; two native Stop cycles returned to Play and left no selected-prefix processes. The native client continued to show Cloud Out of Date because this app exposes `MacAppSupport`, outside Ullage's Windows-root mapper. |
| 4663130 | Normal Golf Game Demo | P | P | I; overlay observed | not configured | P | Fresh Windows-only nested x64 Unity depot. Both native Play cycles reached the rendered streamer-mode surface with `gameoverlayui` attached; confirmed Stop returned cleanly to Play. No shipped-game Steamworks feature calls or Cloud roots were deliberately exercised. |
| 2677470 | POOLS Demo | P | P | I; overlay observed | I (`WinAppDataLocalLow` mapping; no save round trip) | P | Fresh multi-platform Unity/OpenXR depot. Auto mode patched Windows entries 0 and 3 into separate launchers while preserving native macOS/Linux entries. Three native default Play/confirmed-Stop cycles rendered the POOLS menu and returned cleanly; Steam Cloud launch/exit evaluation watched the prefix-side `Tensori/Pools` path and found no matching save files. The OpenXR/BetaKey option was not selected by this macOS session. |
| 2457890 | DRACOMATON | P | P | I; overlay observed | P (`gameinstall` mapped to `MacAppSupport`; two files downloaded and watched) | P | Fresh Windows/macOS Unity depot. Native Play and relaunch rendered the DRACOMATON menu with `gameoverlayui` attached. Native Cloud downloaded and watched `RunData.json` and `SaveData.json` through the owned `MacAppSupport` mapping; both exit evaluations found the files unchanged. Native Stop returned to Play and reaped the selected-prefix helper set. |
| 792100 | 7 Billion Humans | P | F | I | I (`WinAppDataRoaming` mapping; zero watched files) | P | Fresh 226.7 MB win32 depot. Native Play launched the PE32 target, which exited with Wine status 3 before a visible surface; no native Stop event was needed and cleanup was clean. Steam evaluated the `profiles.bin` rule but found no matching file. This matches the Human Resource Machine status-3 boundary. |
| 282800 | 100% Orange Juice | P | P | I; overlay observed | P (`gameinstall`; upload and download proven) | P | Fresh 2.17 GB x64 depot. The title screen rendered in a window-specific capture, while native Steam attached `gameoverlayui`; three native Stop cycles returned cleanly. Native Cloud uploaded generated profiles and `last_save.ojs`, then downloaded the missing save and sidecar back into the mapped root with exact byte restoration. No visible overlay interaction or shipped-game API call is claimed. |
| 2180700 | ABI-DOS | P | F | I; x64 bridge and native Steam transport observed | I (`WinAppDataLocal` mapping; zero watched files) | P | Fresh 514.98 MB x64 GameMaker depot. Native Play reached Running, but Wine showed `CheckMultisampleQualityLevels` with `HRESULT 0x80070057` before a usable surface. Native Stop returned to Play with `wine_exit=137` and a clean prefix; Steam uninstall returned `No Error` and Ullage removed the mapping. |
| 1144770 | SLUDGE LIFE | P | P | I; overlay observed | I (`gameinstall` mapping; no save round trip) | P | Fresh Windows-only x64 Unity depot. Native Play rendered the game's full-screen first-run LOGIN surface and entered Running; native Stop returned cleanly to Play. The first-run gate prevented a gameplay or shipped-game Steamworks acceptance result. |
| 397950 | Clustertruck | P | F | I | not configured (`hidecloudui=1`) | P | Native Play reached the rendered Unity configuration window but no game scene; native Stop returned cleanly with no selected-prefix Wine processes. This remains a title/launcher runtime boundary. |
| 219150 | Hotline Miami | P | F | I | I (`WinMyDocuments` mapping; no save round trip) | P | Native Play launched the 32-bit Windows launcher surface, but its handoff produced no game surface. Direct explicit-entry trials with `HotlineMiami_Original.exe` and `HotlineGL.exe` also failed to render; the OpenGL trial exited with status 53. Native Stop returned the launcher and original-binary attempts to Play with no selected-prefix Wine processes. This remains a title/runtime boundary, not an Ullage mapping or supervision failure. |
| 442070 | Drawful 2 | P | F | P (direct probe) | not configured | P | The valid standalone entry launched through the repaired mapping; the absent `launch_mp.bat` option was hidden with `ullage-disabled`. The shipped game then showed `Application load error 3:0000065432` before a usable surface. A separate x64 probe through the same prefix/runtime passed SteamAPI initialization, identity, ownership, stats enumeration, and shutdown; native Stop cleanup passed. |

### Latest ten-title pass

This bounded pass was performed after the matrix above and is intentionally
separated from the direct feature probe. It validates native Steam transport,
the Cloud mapper where metadata provided a supported Windows root, and the
Stop/cleanup boundary across fresh 32-bit and 64-bit installs. A renderer `I`
or `F` does not weaken a transport result, and a loaded overlay does not prove
that the shipped game called every Steamworks interface.

| AppID | Title | Steamworks transport | Cloud | Lifecycle | Evidence |
| ---: | --- | :---: | --- | :---: | --- |
| 70 | Half-Life | P; i386 lsteamclient and overlay observed | P; native sync/prompt and `gameinstall` mapping | P | Native Play/Stop passed; no changed-save round trip claimed. |
| 312990 | Expendabros | I; i386 lsteamclient and overlay loaded | —; unsupported Windows root | I | Black capture required bridge termination fallback; no native Stop transition claimed. |
| 345820 | Shantae | I; bridge reached the title before Wine status 3 | —; unsupported Windows root | — | Exited before a Stop was needed. |
| 1114290 | Windjammers 2 | P; x64 lsteamclient, overlay, GPTK, and forwarder observed | P; `WinSavedGames` | I | Fullscreen capture stayed black; exact bridge fallback completed. |
| 1213750 | Fight Crab | I; no game-loaded Steamworks handles after graphics initialization failed | P; `WinAppDataLocalLow` | P | Native Stop and clean prefix passed despite the D3D11 device failure. |
| 716490 | EXAPUNKS | P; x64 sidecar, overlay, native Steam client, and forwarder observed | P; `gameinstall` | P | Native Stop returned to Play; no shipped-game API trace claimed. |
| 448510 | Overcooked | P; bridge overlay loaded in the mapped run | P; `WinAppDataLocalLow` | P | Initial native `OS Error 0` was resolved at the Ullage mapping boundary. |
| 1562430 | DREDGE | I; game process did not expose bridge handles | P; `WinAppDataLocalLow` | P | Running, native Stop, and prefix cleanup passed without a renderer surface. |
| 508980 | Crashday Redline Edition | P; overlay, both lsteamclient sides, native Steam client, and `steam_api.dll` observed | P; `WinAppData` | P | Native Stop and uninstall/removal passed. |
| 207140 | SpeedRunners | I; bridge overlay only, no game-loaded lsteamclient handle | —; unsupported Windows root | P | Native Stop returned to Play and prefix cleanup passed. |

The `P` lifecycle result means native Steam emitted an `App Running` transition,
the bridge logged `wine_exit`, and the client returned the AppID to its
installed state. It is not a claim that the game completed a meaningful play
session.

## Current x64 loader-order regression

The public-package Katamari status-5 report was reproduced on this Mac. The
same `lsteamclient.dll` `0xBEEF` signature appeared before the game renderer,
even though the packaged artifacts matched the earlier manually assembled
runtime. Removing the bridge's intermediate shell did not resolve it by
itself; the failure cleared when the package root was restored as the first
`WINEDLLPATH` entry and the computed launch environment was passed directly
to Wine.

Using the unchanged `2026.08.26-3` package with Ullage `72d0c70`, Gravity
Circuit (AppID `858710`) rendered its language-selection surface. The native
Steam overlay libraries were included in the launch transport, but this run
claims transport evidence rather than a visible overlay interaction. Native
Stop returned Steam to Play, the bridge recorded `wine_exit=137`, and the
session receipt reported a clean prefix. This is a bridge-wide x64 launch
regression fix, not a Gravity Circuit workaround; current Katamari and
Megabonk public-package failures remain preserved as pre-fix rows above.
Post-fix Megabonk rendered its default DX11 menu and completed native Stop
cleanup. Post-fix Katamari crossed the former status-5 boundary and completed
native Stop cleanup, but its available desktop capture remained black, so no
current Katamari renderer pass is claimed. The 32-bit Stellar Mess control
also remained healthy after the change.

## Feature-level matrix

| Feature | Current evidence | Status |
| --- | --- | :---: |
| `SteamAPI_Init` | Gravity Circuit's current x64 copied-DLL probe initialized through the packaged runtime with the native Steam client running; the x64 path still uses the canonical-name forwarder staged at the prefix Steam path | P (win32 + current win64 probe) |
| Identity (`ISteamUser::GetSteamID`) | The current Gravity Circuit probe returned logged-on SteamID `76561198352563669`; earlier probes returned a logged-on, nonzero SteamID on both architectures | P (win32 + current win64 probe) |
| Ownership/DRM | The current Gravity Circuit probe returned `subscribed=1` and `subscribed_app=1`; a DRM-wrapper title is not certified | P (win32 + current win64 probe); pending (DRM wrapper) |
| Achievements/stats | The current Gravity Circuit probe requested current stats and enumerated 53 achievements, including state for the first entry; no controlled unlock/store/relaunch test is complete | P (read-only); pending (write path) |
| DLC | The current Gravity Circuit probe called DLC enumeration and returned count 0; no DLC-content launch has been completed | P (enumeration); pending (content) |
| Overlay | The detached Gravity Circuit probe reported `IsOverlayEnabled=0`; visible `gameoverlayui` attachment was observed during native renderer paths, including Gravity Circuit and EXAPUNKS | P (title/renderer-specific) |
| Playtime | Native Steam updates local playtime and App Running/App stopped transitions after bridge runs | P (client telemetry) |
| Steam Stop | Native Steam emitted `App Running,Terminating`; the bridge routed it through its signal trap, reaped the selected prefix, and returned Peggle and Katamari to Play with no Wine/helper processes remaining | P |
| Shutdown/relaunch | The current Gravity Circuit probe reached `SteamAPI_Shutdown`; native Play/Stop runs also returned known titles to Play with no selected-prefix Wine processes remaining | P (win32 + win64/boundary) |

Remaining feature tests should use one known-visible title for the controlled
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

The probe accepts both the newer `SteamInternal_CreateInterface` export and
the legacy `SteamClient` export found in older game API DLLs. On the current
fresh state, copied TIS-100 and EXAPUNKS API DLLs loaded through an ordinary
shell-launched bridge but exited with Wine status 5 during `SteamAPI_Init`.
Because those diagnostic processes were not launched by Steam's Play action,
that result is recorded as a probe-environment limitation, not as a shipped
game feature failure. The native TIS-100 Play run remains the current 32-bit
transport/Stop control.

In the earlier Katamari acceptance run, the 32-bit and 64-bit probes returned
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

The public-package rerun on 2026-08-26 local time intentionally keeps that
earlier feature evidence separate. A fresh Katamari Play crossed the native
Steam boundary and loaded the packaged x64 bridge plus overlay injection, but
the game exited with Wine status 5 before rendering or requiring Stop. A
temporary native-Steam-launched x64 probe loaded Katamari's `steam_api64.dll`
and logged `steam_api_init_begin=1`, then also ended with status 5 before a
completed API result. This is a current title/runtime limitation, not evidence
that the public package passed the x64 feature probe.

The same package was independently exercised with the documented Stellar Mess
win32 control. Native Play reached Running, the native Stop confirmation
returned to Play, and the receipt recorded `native_stop_observed=true`,
`wine_exit=137`, and a clean prefix. A current x64 diagnostic probe now adds
read-only API evidence, but it was a separately staged executable using an
unmodified copy of Gravity Circuit's `steam_api64.dll`; it does not certify
that the shipped game called those interfaces during its native Play session.

The package was also repeated with TIS-100 as a small win32 control. Native
Steam reached Running and returned to Play after the Stop confirmation; the
receipt at `~/.ullage/sessions/370360/last.json` recorded `wine_exit=137`,
`signal_received=true`, and a clean prefix. The page displayed `Steam Cloud
Out of Date` before launch, and the full-display capture was occluded by the
Codex window, so this run adds lifecycle evidence but no new Cloud or renderer
claim.

A fresh Plants vs. Zombies (AppID `3590`) Windows depot was downloaded to the
external library and launched through the unchanged package on 2026-08-27. The
title screen rendered, the x86 lsteamclient path loaded, and
`gameoverlayui -gameid 3590` attached to the game process. The fullscreen game
occluded the Steam Helper capture, so the native Stop button could not be
reached from a fresh screenshot; quitting Steam instead exercised the generic
client-exit fallback. The receipt recorded `steam_client_exit_observed=true`,
`signal_received=true`, `wine_exit=137`, one reaped game process, eight reaped
helpers, and a clean prefix. The title has no supported Windows Cloud root, so
no Cloud claim is made. Steam then uninstalled the 54 MB depot and Ullage
restored the original launch entry.

Eets (AppID `6100`) supplied a current win32 renderer and native-Stop control
with the same public package. Its fresh 143 MB Windows depot rendered the
main menu, and the bridge log recorded the x86 runtime and Steam transport
injection. No `gameoverlayui` process attached during the run, so this is
indirect transport evidence rather than a visible overlay claim. The healthy
`gameinstall` mapping used zero seeded files, while Steam's native cloud log
explicitly reported `Sync Disabled` and `AutoCloud is disabled`; no Cloud
upload or round trip is claimed. Native Stop produced the expected
`App Running` -> `Terminating` -> `Fully Installed` transition, and the
receipt recorded `native_stop_observed=true`, `wine_exit=137`, and a clean
prefix. Steam then uninstalled the depot with `No Error`, Ullage removed the
mapping and launch state, and the small residual test directory was moved to
the macOS Trash; the appinfo backups remain available for provenance.

A current-package repeat with the existing Peggle Deluxe install (AppID
`3480`) supplied a second win32 transport control without another download.
Native Play launched the mapped `peggle.exe` and PopCap child, the fullscreen
surface rendered its loading screen, and `gameoverlayui -gameid 3480` attached.
The title remained on that screen for roughly one minute at high child CPU,
so no full-menu renderer pass is claimed. Fullscreen occlusion prevented a
fresh native Stop click; quitting Steam exercised the generic client-exit
fallback. The receipt recorded `steam_client_exit_observed=true`, one reaped
game process, eight reaped helpers, `wine_exit=137`, and a clean prefix. The
existing depot was preserved and Ullage restored the original Steam launch
entry after the run; no Cloud claim applies because the title has no
supported Windows root.

Peggle Extreme (AppID `3483`) exposed a separate generalized appinfo edge on
the same current package. Its Windows depot records a relative
`PeggleExtreme.exe` launch without either a launch or common `oslist`; the
mapper previously rejected it as having no usable Windows PE launch. Commit
`be02c66` now treats a platformless relative `.exe` as the Windows signal while
continuing to reject explicit non-Windows annotations, with installed and
catalog fixture coverage. The fresh 22 MB depot then launched through native
Steam and rendered the Extreme title screen; x86 lsteamclient and
`gameoverlayui -gameid 3483` were observed. Fullscreen occlusion prevented a
native Stop click, so the native Steam client-exit fallback reaped one game
process and eight helpers; the receipt recorded
`steam_client_exit_observed=true`, `wine_exit=137`, and a clean prefix. Steam
uninstalled the depot and Ullage removed the mapping. The overlay process was
observed but no visible overlay interaction is claimed, and the title has no
Cloud feature claim here.

DRACOMATON (AppID `2457890`) supplied a current win64 renderer, overlay
attachment, native Stop, and Cloud control with the unchanged public package.
The healthy `gameinstall` mapping let native Steam reconcile a pre-launch local
divergence by downloading the existing remote `SaveData.json`, then watch the
real `RunData.json` and `SaveData.json` files. A reversible marker edited while
the game was running uploaded successfully on native Stop, together with the
`._SaveData.json` AppleDouble sidecar created by the external MS-DOS FAT32
library. Restoring the original 6,261-byte save and repeating native Stop
uploaded the original bytes as the final Cloud state. This proves both native
Cloud directions while preserving the user's save; the sidecar remains a
host-filesystem artifact to account for in future FAT32 tests. Steam
uninstalled the depot with `No Error`, preserving the small save/config
directory, and Ullage removed the mapping cleanly.

8-Bit Bayonetta (AppID `567090`) supplied a small current win32 control with
the public package. Native Play reached Running through the guarded `8BB.exe`
entry; Unity logged a D3D11 device-creation failure followed by a D3D9 device,
and process inspection showed Steam's `steamloader.dylib` and
`gameoverlayrenderer.dylib` loaded into the game. The game surface was not
frontmost in the desktop capture, so this is renderer initialization and
transport evidence, not a visible-menu or overlay-interaction claim. The
title has no native Cloud roots in the current appinfo. Native Stop returned
to Play with a clean prefix; Steam uninstalled the depot with `No Error` and
Ullage removed the mapping.

7 Billion Humans (AppID `792100`) supplied a small Windows-specific Cloud
control. The fresh 226.7 MB depot contained a PE32 `7 Billion Humans.exe`
target and a `WinAppDataRoaming` rule for `profiles.bin`; the current package
installed the mapping and native Steam launched the target. The process exited
with Wine status 3 before a visible renderer appeared, with no residual
processes and a clean prefix. Native Cloud resolved the mapped root but found
zero files to watch because this fresh run created no `profiles.bin`, so no
transfer claim is made. Steam uninstalled the depot with `No Error` and Ullage
removed the mapping. The status-3 result matches the existing Human Resource
Machine boundary, so no per-title workaround or Ullage source change is
justified.

100% Orange Juice (AppID `282800`) supplied the strongest current x64 Cloud
control. The fresh 2.17 GB depot contained a PE32+ `100orange.exe` target; the
current package rendered its title screen, native Steam attached
`gameoverlayui`, and three confirmed native Stop cycles returned to Play with
clean prefixes. Native Cloud uploaded the generated `profile0.ojs`,
`profile1.ojs`, `profile2.ojs`, and later `last_save.ojs` files plus the
FAT32-generated AppleDouble sidecars. Moving only the newly generated
`last_save.ojs` out of the mapped tree made native Steam download both the
logical save and sidecar back successfully, restoring the exact 17-byte save.
The title window was offset behind other macOS apps, so a window-specific
capture was required; no visible overlay interaction or shipped-game API call
is claimed. Steam uninstalled the depot with `No Error`, Ullage removed the
mapping, and the generated residue was moved to recoverable Trash.

ABI-DOS (AppID `2180700`) supplied a small current x64 GameMaker control with
a `WinAppDataLocal` root. The fresh depot launched through the current
package and native Steam, but Wine displayed the title's
`CheckMultisampleQualityLevels` error with `HRESULT 0x80070057` before a usable
surface. Native Cloud evaluated `ABI_DOS/*` and watched zero files rather than
claiming a transfer. The native Stop event returned the page to Play with a
clean prefix, and Steam uninstall plus Ullage removal completed with `No
Error`. This repeats the existing GameMaker graphics boundary, so no
title-specific workaround or Ullage source change is justified.

SPY Fox in: Cheese Chase (AppID `292280`) supplied a current win32 install,
mapping, native Play, and process-level overlay control with the unchanged
public package. The bundled ScummVM 2.1.0 config requested an invalid renderer
mode for this host, left the first-run updater enabled, and selected an
unavailable Windows MIDI device; the original run therefore remained at the
fullscreen setup surface. A reversible test-only config using `gfx_mode=1x`,
`updates_check=0`, and `music_driver=auto` reached a visible scene and was
followed by exact restoration of the depot config. The Steam Helper could not
expose controls inside the fullscreen Wine window, so Steam client exit
exercised the generic fallback and left a clean prefix. Steam uninstalled the
depot with `No Error`, Ullage removed the mapping, and no Cloud round trip is
claimed because no save was modified.

911 Operator (AppID `503560`) supplied a current win32 Unity control with two
Windows launch entries. The fresh ~1.05 GB depot mapped a
`WinAppDataLocalLow` Cloud root. Native Play launched `911.exe` through the
current package; the title's Unity selector initially required a test-only
in-prefix Windows message probe because this rotated macOS display did not
accept shell-level CGEvent input. After the selector's `Play!` button was
activated, a window-specific capture showed the rendered introductory surface.
The game log recorded a D3D11 failure followed by D3D9/NVIDIA GeForce 6800
initialization, and native Steam attached `gameoverlayui`. A Shift+Tab probe
did not produce a separately capturable overlay panel, so no visible overlay
interaction is claimed.

The Steam chooser's `Launch Edit Calls!` entry also launched `CallEditor.exe`
through its generated entry-specific launcher and rendered the editor surface.
Its Unity log reached Steamworks.NET workshop callback code
(`SteamAPI_RunCallbacks`, `WorkShopTest`) and reported zero workshop XML
files. Both entries were stopped through native Steam with
`native_stop_observed=true`, `wine_exit=137`, and clean prefixes. Native Cloud
evaluated the `WinAppDataLocalLow` rule on launch and exit but watched zero
files on both fresh runs, so no transfer claim is made. Steam uninstalled the
depot with `No Error` and Ullage removed the mapping.

198X (AppID `1086010`) supplied a current x64 renderer and lifecycle control
with the same public package. The fresh 500.66 MB depot had no supported
Windows Cloud root, so `--cloud-native` correctly refused the plan; the
ordinary mapping remained healthy. Native Play rendered the title menu twice,
with `gameoverlayui` attached on both runs. Both native Stop cycles returned
Steam to Play with `native_stop_observed=true`, `wine_exit=137`, eight helpers
reaped, and clean prefixes. No shipped-game Steamworks feature or visible
overlay interaction is claimed. Steam uninstalled the depot with `No Error`
and Ullage removed the mapping.

100 Korea Cats (AppID `2932930`) supplied a small current x64 renderer and
lifecycle control with the unchanged public package. The appinfo record has no
supported Windows Cloud root, so the ordinary launch mapping was used. Native
Play rendered the title's monochrome line-art menu with `gameoverlayui`
attached. Native Stop returned Steam to Play with
`native_stop_observed=true`, `wine_exit=137`, eight helpers reaped, and a clean
prefix. No shipped-game Steamworks feature or visible overlay interaction is
claimed. Steam uninstalled the depot with `No Error` and Ullage removed the
mapping.

Shipped (AppID `1037190`) supplied a current x64 Unity renderer and lifecycle
control with the unchanged public package. The first window-specific capture
was black during startup, but a bounded wait reached the rendered Controls
screen. The game process had Steam's loader and overlay renderer libraries;
`gameoverlayui` attached later in the run. Native Stop returned Steam to Play
with `native_stop_observed=true`, `wine_exit=137`, eight helpers reaped, and a
clean prefix. No shipped-game Steamworks feature or visible overlay
interaction is claimed. Steam uninstalled the depot with `No Error` and Ullage
removed the mapping.

Cold Silence (AppID `1003830`) supplied a small current x64 GameMaker control
using the unchanged public package. Steam downloaded a fresh 52.93 MB depot
to the external library, and `ullagectl install` created a healthy ordinary
mapping because its `WinAppDataLocal` rule is supported but no save was
created. Native Play reached the mapped executable and loaded the x64
lsteamclient sidecar, Steam's loader, and overlay renderer, but the title
stopped at a Wine-owned GameMaker `CheckMultisampleQualityLevels` dialog with
`HRESULT 0x80070057` before a usable surface. This repeats the ABI-DOS
GameMaker graphics boundary and does not justify a title-specific workaround
or Ullage source change. Native Stop returned Steam to Play with
`native_stop_observed=true`, `wine_exit=137`, and a clean prefix. Steam
uninstalled the depot with `No Error`; after Steam quit, Ullage removed the
mapping and left no depot residue. No shipped-game Steamworks feature or
visible overlay interaction is claimed.

Beyond Minimalism (AppID `861320`) supplied a small current win32 control
using the unchanged public package. The CEF Helper's visible `INSTALL`
button did not start a download through the computer-use coordinate path, so
the native `steam://install/861320` URI opened the same Steam install modal;
this is a Steam CEF automation boundary, not a changed Ullage install path.
The fresh 51.01 MB depot mapped cleanly after Steam restarted. Native Play
opened the title's `BeyondMinimalism Configuration` dialog, and a temporary
scoped in-prefix Windows message probe activated its `Play!` button. A
window-specific capture then showed the rendered title screen, with x86
lsteamclient, Steam's loader/overlay renderer, and `gameoverlayui` observed.
Native Stop returned Steam to Play with `native_stop_observed=true`,
`wine_exit=137`, and a clean prefix. Steam uninstalled the depot with
`No Error`; after Steam quit, Ullage removed the mapping and left no depot
residue. No shipped-game Steamworks feature or visible overlay interaction is
claimed.

Brain Storm: Tower Bombarde (AppID `669750`) supplied a fresh 6.71 MB win32
control using the unchanged public package. The mapped native Play request
reached Running, and the x86 Steam transport plus `gameoverlayui` were
observed. The title exposed a hidden `LoadForm` and a 1x1 game window rather
than a usable surface, so this is a transport/lifecycle control, not a
renderer pass. Native Stop returned Steam to Play with
`native_stop_observed=true`, `wine_exit=137`, and `prefix_clean=true`.
Steam uninstalled the depot with `No Error`; after Steam quit, Ullage removed
the mapping and left no depot residue. No supported Windows Cloud root,
shipped-game Steamworks feature, or visible overlay interaction was claimed.

The current-package Cloud fixture checks also exposed a test-harness boundary,
not a mapper defect. Gravity Circuit's mapped `WinAppDataRoaming` tree was
empty; a unique `.sav` fixture was present before native Play, but Steam's
launch pass watched zero files and the fullscreen client-exit fallback ended
the run before a Cloud exit evaluation. EXAPUNKS provided the complementary
control: native Steam watched its existing `save.dat`, while a unique
`.solution` fixture was left for exit evaluation; fullscreen occlusion again
required the client-exit fallback before that evaluation. Both fixtures were
removed afterward, and neither run is counted as upload or round-trip evidence.

The current Gravity Circuit x64 probe ran on 2026-08-27 with the unchanged
public package `2026.08.26-3` and an unmodified copy of the depot's
`steam_api64.dll`. It returned `steam_api_load=1`, `steam_api_init=1`, a
matching AppID (`858710`), logged-on identity, subscription/ownership,
`dlc_count=0`, `request_current_stats=1`, `achievement_count=53`, and
`steam_api_shutdown=1`. The bridge receipt ended with `wine_exit=0` and a
clean prefix. This is intentionally a diagnostic API result, not a modified
depot or shipped-game trace. Its `overlay_enabled=0` result is kept separate
from the visible `gameoverlayui` process observed in native game runs; the
probe itself was not a visible overlay interaction test.

EXAPUNKS (AppID `716490`) supplied a current Cloud/lifecycle near-miss with
the same package. The healthy `gameinstall` mapping was installed, Steam's
content log showed `SynchronizingCloud` before launch, and `gameoverlayui`
attached to the x64 Wine process. The title remained on its loading surface,
so no renderer pass is claimed. Quitting Steam exercised the generic client
exit fallback and left a clean prefix, but the client exited before a normal
Cloud exit evaluation; no changed-file upload or round-trip claim is made.

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

A separate current x64 Gravity Circuit run exercised the native-client exit
boundary. Quitting Steam while the game was active caused the native waiting
dialog, then the client exited; Ullage's exact `steam_osx` watcher observed the
exit and routed it through the same signal/reaper path. The receipt recorded
`steam_client_exit_observed=true`, `native_stop_observed=false`,
`wine_exit=137`, and `prefix_clean=true`, with no selected-prefix processes
remaining. This validates cleanup after client shutdown; it is not a new
Steamworks feature or a substitute for the AppID-scoped native Stop event.

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
