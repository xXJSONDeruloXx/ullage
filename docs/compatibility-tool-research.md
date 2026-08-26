# Steam compatibility-tool boundary

Research snapshot: 2026-08-25.

## Decision

Do not make Ullage a native macOS Steam compatibility tool yet. The current
macOS client reads and logs `CompatToolMapping`, but it does not invoke a
registered tool when a Windows launch entry is played. The existing appinfo
launch mapping is therefore still the only proven launch boundary.

The host's global depot setting remains in place:

```text
@sSteamCmdForcePlatformType windows
```

This is a negative compatibility-tool result, not a reason to add a second
dispatcher, UI injection, or a Proton fork.

## Current proven path

```text
native macOS Steam
        |
        | appinfo launch entry
        v
~/.ullage/launchers/APPID.sh
        |
        v
ullage-bridge -> Wine/GPTK -> Windows PE game
        |
        v
lsteamclient -> native Steam session
```

`ullage-install` edits the binary `appcache/appinfo.vdf` only while Steam is
fully stopped, writes generated launch state under `~/.ullage`, and asks for a
Steam restart before Play. The game executable and depot remain untouched.
`ullage-bridge` preserves the native Steam transport by default and supervises
the exact Wine launcher, Steam's AppID-scoped termination event, and the
selected prefix's helpers.

This restart is a consequence of the appinfo edit. It is not caused by Wine,
GPTK, lsteamclient, or normal game shutdown.

## Native macOS dispatch experiment

The experiment used Peggle Deluxe (AppID 3480), whose appinfo still contained
the native Windows launch executable `peggle.exe`. A disposable tool was placed
in the macOS Steam scan directory:

```text
~/Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/MacOS/
  compatibilitytool.d/Ullage Probe/
    compatibilitytool.vdf
    toolmanifest.vdf
    ullage-probe
```

The manifest declared `from_oslist=windows`, `to_oslist=macos`, and a minimal
`toolmanifest.vdf` commandline. The probe only recorded its invocation and
then slept; it did not call Wine or modify any game state.

Steam build `1785799196` was fully stopped before each mapping change and
restarted afterward.

| Mapping trial | Steam log | Probe invocation | Play result |
| --- | --- | --- | --- |
| global AppID `0` -> `ullage-probe` | mapping recorded | none | Steam tried raw `peggle.exe`; `OS Error 0` |
| AppID `3480` -> `ullage-probe` | mapping recorded | none | Steam tried raw `peggle.exe`; `OS Error 0` |

The Steam `compat_log.txt` entries prove that the client parsed the mapping:

```text
Mapping AppID 0 to tool "ullage-probe" with priority 250
Mapping AppID 3480 to tool "ullage-probe" with priority 250
```

But neither trial created the probe's invocation log, a Wine process, or a
compatibility-tool launch. Native Steam's console log showed the direct
`peggle.exe` path followed by `Failed to spawn process` and `AppError_46`.

This distinguishes registration from dispatch:

```text
macOS Steam reads CompatToolMapping  -> proven
macOS Steam invokes the tool         -> disproven on this client/build
```

The temporary tool and the pre-test config snapshot were moved out of Steam
and preserved under `~/.ullage/experiments/compat-dispatch/`. The mapping was
removed, `compat.vdf` was left unchanged, and the Windows depot override was
verified still present.

## What this rules out

The following are not safe production changes based on this evidence:

* Adding `compatibilitytool.d/Ullage` and expecting native macOS Steam to
  route Play through it.
* Writing global or per-AppID `CompatToolMapping` entries as a substitute for
  the appinfo launch mapping.
* Removing the global Windows depot setting because a compatibility tool is
  registered.
* Editing `appinfo.vdf` while Steam is running to avoid the restart.

Proton Selector's stable tool directory is useful prior art for Linux Steam,
where the client actually dispatches compatibility tools. Valve's Proton
manifest/template and Proton Selector's dispatcher do not establish a macOS
launch contract. Kaon's macOS findings motivated this experiment, but the
local no-op result is the stronger evidence for this client.

## Review disposition

The attached stable-tool proposal remains a reasonable future design only
behind a new positive dispatch result. It should not drive a broad refactor
now.

Keep the current small boundaries:

* native Steam remains the control plane;
* `ullage-install` and `ullage-remove` own offline appinfo transactions,
  backups, and restart warnings;
* `ullage-mapping.py` reports and conservatively repairs stale mappings;
* `ullage-bridge` owns Wine/GPTK launch, transport preservation, Stop
  supervision, and prefix-scoped cleanup;
* generated state stays under `~/.ullage`, outside the checkout.

The current code already incorporates the useful review safeguards: private
backup permissions, ambiguous Wine-user failure, prefix-scoped Cloud paths,
non-base64 Cloud file transfer, and shell tests for signal/Stop races. Moving
the installer into a Python package or adding a generic compatibility-manager
abstraction would increase surface area without unlocking a path the native
client currently ignores.

## Reconsideration gate

Revisit this design only if a future macOS Steam build or a maintained shim
proves all of the following with a harmless tool first:

1. Steam invokes the tool for a per-AppID mapping.
2. The tool receives the original Windows executable, arguments, AppID, and
   Steam transport environment.
3. A newly downloaded Windows depot can be played without an appinfo rewrite.
4. Native Stop, playtime, Steamworks, overlay, and relaunch remain intact.
5. The tool can fail or be removed without corrupting other AppIDs.

Only then should the existing bridge be adapted behind a stable tool identity.
Until then, the lower-risk optimization is batching appinfo mappings while
Steam is already stopped or automating the required restart—not live metadata
edits.

## Title-local renderer adapters

The launch boundary can select a native Windows DLL for one AppID without
changing the shared prefix. `ullage-install --wine-dll-overrides VALUE`
persists the value in that AppID's generated config, and an explicit bridge
argument overrides it for a diagnostic run. The DLL still has to be supplied
in the Windows loader search path, normally the game's own directory.

This was exercised with Oddworld: Abe's Exoddus (AppID 15710), whose Wine 11.0
DirectDraw path rejected the game's requested 640x480x8 mode. The maintained
[cnc-ddraw](https://github.com/FunkyFr3sh/cnc-ddraw) wrapper was placed in the
title directory and selected with `ddraw=n,b;lsteamclient=b`. The native Steam
Play path rendered the game's intro and menu, native Stop returned to Play,
relaunch rendered again, and both runs left no Wine or game processes. The
wrapper was a host experiment; it is not bundled or copied into Ullage.

## Sources and prior art

* [Valve Proton](https://github.com/ValveSoftware/Proton)
* [Valve compatibility-tool template](https://github.com/ValveSoftware/Proton/blob/proton_11.0/compatibilitytool.vdf.template)
* [Proton Selector](https://github.com/GloriousEggroll/proton-selector)
* [Kaon macOS Steam prior art](https://github.com/natbro/kaon)
* [Steamworks depot mounting rules](https://partner.steamgames.com/doc/store/application/depots)
* [Valve Steam-for-Linux `CompatToolMapping` issue](https://github.com/ValveSoftware/steam-for-linux/issues/10184)
