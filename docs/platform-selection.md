# Per-AppID Windows depot selection

## Current decision

No native macOS Steam mechanism has been proven to select Windows depots for
one AppID while leaving the rest of the library on native platform selection.
Ullage therefore keeps the host's early global setting:

```text
@sSteamCmdForcePlatformType windows
```

This is deliberately a Steam-client configuration, not an Ullage launch-time
override. Removing it without an equivalent selection path lets native Steam
reconcile installed content against macOS depots.

## What the metadata can and cannot do

Valve's depot rules select OS-specific depots from the client platform. An
AppID's `config/launch/*/config/oslist` controls which launch options are
eligible; it is separate from each depot's `config/oslist`. Editing a Windows
launch entry can make a Play action point at a Windows executable, but it does
not make native macOS Steam download the Windows depot. See the [Steamworks
depot mounting rules](https://partner.steamgames.com/doc/store/application/depots).

Native Steam also contains a compatibility-manager path. Its local
`compat.vdf` cache uses entries shaped like this:

```text
"platform_overrides"
{
    "<appid>"
    {
        "dest" "macos"
        "src"  "windows"
    }
}
```

The native client binary contains the corresponding load, flush, get, and set
methods. That proves the cache is real; it does not prove that native macOS
Steam runs the Linux Steam Play decision path. A separate `CompatToolMapping`
block selects a named compatibility tool on Linux; it is not itself a depot
selector. The [Valve Steam-for-Linux issue describing that mapping](https://github.com/ValveSoftware/steam-for-linux/issues/10184)
is useful prior art, but it does not establish macOS behavior.

## Reversible Steam experiment

The experiment used Peggle Deluxe (AppID 3480), which has separate Windows and
macOS depots. The original Windows install was snapshotted before changing
Steam state. Each trial removed the app manifest and install directory, then
used native Steam's `app_install 3480` path.

| Trial | Global setting | Per-AppID cache | Result |
| --- | --- | --- | --- |
| Control | absent | empty | macOS depot 3489, manifest `3251107157334717608`, 31,436,826 bytes |
| Candidate | absent | `3480: dest=macos, src=windows` | macOS depot 3489, same manifest and size |
| Restored | present | empty | Windows depot 3481, manifest `3233322151779281130`, 19,463,282 bytes |

The candidate override therefore had no observable effect on depot selection.
The control phase also showed the safety problem with removing the global
setting: other dual-platform installs began being reconciled toward macOS
content. Restoring the setting and allowing Steam to finish its repair queue
returned the affected installs to their Windows depots:

| AppID | Depot |
| ---: | ---: |
| 304430 | 304432 |
| 334940 | 334941 |
| 356400 | 356401 |
| 584400 | 584401 |
| 609320 | 609322 |

The preserved host artifacts are under
`~/.ullage/experiments/per-appid-platform/`. The global setting remains in
place after the experiment.

## Compatibility-tool follow-up

The result rules out two tempting changes:

* changing `appinfo.vdf` launch `oslist` or executable fields as a depot
  selector;
* writing a `compat.vdf` platform override without an active compatibility
  tool and Steam Play backend.

That compatibility-tool probe is now complete. A disposable
`from_oslist=windows`, `to_oslist=macos` tool was registered in the native
client's observed macOS scan directory and selected first globally, then for
Peggle Deluxe (AppID 3480). Steam logged both mappings, but never invoked the
tool; Play attempted the raw Windows executable and failed with `OS Error 0`.
The full protocol and preserved artifact location are in
[`compatibility-tool-research.md`](compatibility-tool-research.md).

This rules out using `CompatToolMapping` as a production replacement for the
current appinfo launch mapping on this client/build. Keep the global Windows
override and the offline appinfo transaction until a future client provides a
positive dispatch result.

An external SteamCMD/DepotDownloader command scoped to one AppID remains a
possible content-acquisition workaround, but it would not be native Steam's
install/update/verification control plane and is not a replacement for the
proven launch path.
