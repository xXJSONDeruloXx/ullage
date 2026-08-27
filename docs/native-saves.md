# Native save evidence and boundaries

This document records what Ullage currently proves about Windows save data on
macOS. It covers Steam Auto-Cloud path mapping through native Steam; it does
not claim that every game-specific save system or renderer works.

## What is known

Native Steam remains the Cloud control plane. Ullage adds a local Windows UFS
root override and a prefix-scoped symlink, then lets Steam perform its normal
download, upload, hashing, cache, badge, and conflict behavior. Ullage does
not edit `remotecache.vdf` to manufacture a Cloud result and does not use a
browser, token, or per-file transfer fallback.

The mapper has explicit destinations for every Windows root currently present
in the local Steam appinfo inventory and in the documented Auto-Cloud model:

| UFS root | Wine destination |
| --- | --- |
| `WindowsHome` | `drive_c/users/<user>` |
| `WinMyDocuments` | `drive_c/users/<user>/Documents` |
| `WinAppDataLocal` | `drive_c/users/<user>/AppData/Local` |
| `WinAppDataLocalLow` | `drive_c/users/<user>/AppData/LocalLow` |
| `WinAppDataRoaming` | `drive_c/users/<user>/AppData/Roaming` |
| `WinSavedGames` | `drive_c/users/<user>/Saved Games` |
| `WinProgramData` | `drive_c/ProgramData` |
| `SteamCloudDocuments` | `drive_c/users/<user>/Documents/Steam Cloud/<login>/<game>` |
| `gameinstall` | the Steam install directory |

The path resolver rejects traversal and the native mapper rejects an unknown
Windows-prefixed root instead of guessing. Mac/Linux roots in a mixed record
describe native-platform alternatives and are ignored for the forced Windows
prefix. A record with no recognized Windows/all-platform root is rejected by
`--cloud-native`.

The following behavior is covered by tests or real runs:

* Unit tests cover every supported root, mixed-root records, account-name
  discovery, account-ID substitution, path traversal, guarded symlink cleanup,
  rollback, and unknown-root rejection.
* Sonic Mania exercised `WinAppDataLocal` and `SteamCloudDocuments`; native
  Steam created `steam_autocloud.vdf` below the prefix-side Windows Documents
  path.
* FAR: Lone Sails exercised a 64-bit Unity depot with a nested executable and
  `WinAppDataLocalLow`.
* Thumper exercised `gameinstall` and native Steam watched its existing save
  files through the install-directory mapping.
* Katamari Damacy REROLL, JellyCar Worlds, RACCOON, Sonic Mania, and FAR: Lone
  Sails showed the ordinary native Steam Cloud state after mapping. RACCOON
  also completed a reversible changed-file upload round trip.
* Gravity Circuit exercised a nested x64 depot with `WinAppDataRoaming`; the
  native page showed the checked Cloud state and the mapping was restored after
  the depot was uninstalled. No game save was created during that run.
* EXAPUNKS exercised a nested x64 depot with a `gameinstall` root on the current
  public package. The native mapper installed the healthy game-install link and
  Steam logged `SynchronizingCloud` before launch. The existing `save.dat` was
  preserved, but the title stayed on its loading surface and the native client
  was quit before Cloud exit evaluation, so no changed-file upload or round
  trip is claimed.
* Eets exercised a healthy `gameinstall` mapping on the current public package,
  but Steam's native log explicitly marked the session `Sync Disabled` and
  `AutoCloud is disabled`; the watched-file set was empty and
  `remotecache.vdf` was deleted as empty. This is a title/client capability
  boundary, not a successful Cloud transfer, so no upload or round trip is
  claimed.
* DRACOMATON exercised a current win64 `gameinstall` mapping on the public
  package. Native Steam downloaded and watched its two real JSON saves, skipped
  both as unmodified on exit, and completed an upload of macOS AppleDouble
  `._*.json` sidecars created on the external MS-DOS FAT32 library. This is
  successful native Cloud transfer evidence, but not a changed-save round trip;
  the sidecars are a host-filesystem artifact to account for when testing
  `gameinstall` roots on non-APFS volumes.
* A stale local Steam Cloud cache can seed a missing prefix file once when the
  file satisfies the current UFS pattern and size/SHA-1 check. Existing prefix
  files are never overwritten by that seed path.
* The current local appinfo inventory contains one `WindowsHome` title,
  Stellar Blade. Its exact `WindowsHome` plus `WinAppDataLocal` layout is
  covered by a fixture; it has not had a live Ullage run because it is not
  installed on this host.
* Operation Valor's full app (`1095480`) declares Cloud entries for
  `WindowsHome` and the other Windows roots, but the locally added Operation
  Valor Demo (`1107960`) has no UFS section and therefore cannot validate
  Steam Cloud.

The native Steam badge is authoritative. A prefix file being present proves
path placement; a synchronized badge proves what native Steam believes about
the Cloud state. Neither result alone proves that a game writes the expected
save during play.

## Remaining TODOs

These are validation gaps, not alternate Cloud implementations:

- [ ] A live `WindowsHome` title, preferably one with a changed-file round trip.
- [ ] Divergent local and remote saves, including the native Steam conflict dialog,
  keep-local, keep-remote, and cancel/retry outcomes.
- [ ] Download, upload, and badge behavior after Steam rewrites `appinfo.vdf` and
  Ullage repairs the mapping.
- [ ] Multiple Steam login records and a real `{Steam3AccountID}` or
  `{64BitSteamID}` save path in a native run.
- [ ] Multiple patterns, recursive patterns, path transforms, unusual separators,
  and files at the root of `WindowsHome` in real titles.
- [ ] Titles that set `hidecloudui`, `ignoreexternalfiles`, use only Mac/Linux
  roots, or store state in the registry, an external service, or a proprietary
  sync API.
- [ ] Native Cloud behavior when the prefix is moved, recreated, or contains more
  than one plausible Wine user.
- [ ] Per-AppID Windows depot selection. The current host still relies on the
  global `@sSteamCmdForcePlatformType windows` setting; the negative native
  Steam experiment is recorded in [`platform-selection.md`](platform-selection.md).
- [ ] Any future Steam root whose name is not in the explicit table. It should be
  added with a documented destination, fixture, and one real acceptance run;
  silently mapping it would risk syncing the wrong files.

The first item is the highest-value remaining save test. The other items can
remain TODOs while the native path continues to delegate transfer and
conflict policy to Steam.

See the [Steam Cloud documentation](https://partner.steamgames.com/doc/features/cloud)
for Valve's root and override model, and
[`steamworks-acceptance.md`](steamworks-acceptance.md) for the broader launch
and Steamworks evidence matrix.
