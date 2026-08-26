# Usage

Ullage edits one local Steam launch entry so the native macOS Steam Play
button invokes an external launcher. Steam must be fully quit while
`appcache/appinfo.vdf` is edited.

## Requirements

* Native macOS Steam configured to retain Windows depots:

  ~~~text
  @sSteamCmdForcePlatformType windows
  ~~~

  Ullage does not edit this setting or manage depot selection.
* A prepared Wine prefix with `system.reg`. Use one prefix per AppID while the
  lifecycle and reaper work remains experimental.
* Wine, GPTK/D3DMetal, and compatible lsteamclient artifacts matching the
  [runtime contract](../runtime/README.md).
* Native Steam's `steamclient.dylib`.
* For 64-bit games, the staged `steamclient64.dll` forwarder described by the
  runtime contract.

## Build and check

~~~sh
make
make check
~~~

## Install

Pass explicit runtime roots so the repository does not select a provider or
GPTK build implicitly:

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

`--install-dir` is Steam's game root; `--game-dir` is the Wine process working
directory. For a nested executable such as `windows/Game.exe`, keep
`--install-dir` at the Steam install directory so the patched launch entry is
calculated relative to the depot root.

When `--game-dir` is omitted, a launch entry's appinfo `workingdir` is used
when it points to an existing directory inside the depot. An explicit
`--game-dir` overrides that metadata for every generated option.

Without `--launch-entry`, Ullage maps every Windows `.exe` launch option in
the appinfo record whose executable is present in the installed depot to a
small entry-specific launcher. That keeps Steam's native option chooser intact
while allowing options that select a different executable or working
directory. Optional entries advertised by Steam but absent from the installed
depot are left untouched. Entries whose executable or working directory is
outside the depot are also left untouched. Use `--launch-entry KEY` when a
title's launcher is not a direct Windows PE executable or when only one option
should be redirected.

Use these options only when needed:

* `--arch win32` or `--arch win64` overrides PE detection.
* `--wine-dllpath` supplies an alternate colon-separated Wine/D3D library path.
* `--wine-dll-overrides` persists a per-AppID `WINEDLLOVERRIDES` value. Use it
  when a title-local native DLL, such as a DirectDraw compatibility wrapper,
  must replace a Wine builtin; the DLL itself remains outside Ullage.
* `--legacy-steam` selects the older Steam DLL set in a prepared prefix.
* `--clean-steam-transport` disables descriptor preservation for a title-specific
  diagnostic.
* `--launch-entry KEY` selects a numeric cached launch entry when Steam names a
  wrapper or stale executable instead of the target PE.
* `--cloud-wine-user NAME` selects a nonstandard Wine user; `auto` reads
  `user.reg` and otherwise requires an unambiguous prefix user.
* `--cloud-steam-account-name NAME` selects a login record when Steam has more
  than one account.

Restart Steam after installation and press its ordinary Play button. The
generated launcher receives Steam's arguments. The bridge waits for the exact
Wine launcher, waits for the selected prefix's Wine session to become idle,
and then reaps only prefix-owned helpers.

`--cloud-native` is the supported native Auto-Cloud path. It maps Windows UFS
roots into the prefix and leaves transfer, hashing, conflict handling, and the
Cloud badge to Steam. See [Native saves](native-saves.md) for the root table and
evidence ledger.

## Stop behavior

The macOS client records the external launcher but does not signal it directly
when Stop is pressed. By default, Ullage watches native Steam's
`logs/content_log.txt` from the launch-time offset for the active AppID's
`Terminating` state. It routes that event through the same supervisor and
prefix-scoped cleanup path. Set `STEAM_STOP_WATCH=0` only for diagnostics.

## Inspect and repair

Steam can regenerate `appcache/appinfo.vdf` during a metadata refresh. Mapping
status is read-only:

~~~sh
"$HOME/Developer/ullage/bin/ullage-mapping.py" status \
  --appid APPID \
  --steam-root "$HOME/Library/Application Support/Steam"
~~~

`healthy` means the recorded launch entry, generated config, and launcher
agree. `stale` means Steam restored the native executable; `foreign` means a
different local change owns the entry; `broken` means generated state is
incomplete.

After fully quitting Steam, repair a stale mapping atomically:

~~~sh
"$HOME/Developer/ullage/bin/ullage-mapping.py" repair \
  --appid APPID \
  --steam-root "$HOME/Library/Application Support/Steam"
~~~

Repair backs up appinfo under `~/.ullage/backups/appinfo`, uses the recorded
entry as an optimistic concurrency check, and refuses to overwrite a foreign
mapping unless `--force` is explicit. It does not recreate missing runtime
state; reinstall or restore that state first.

## Remove

Quit Steam, then restore the original launch entry:

~~~sh
"$HOME/Developer/ullage/bin/ullage-remove" \
  --appid APPID \
  --steam-root "$HOME/Library/Application Support/Steam"
~~~

Generated launchers, mapping state, backups, prefixes, and logs live under
`~/.ullage` by default. `ULLAGE_STATE_DIR` or `--state-dir` selects another
state root. Removal is recoverable and only removes symlinks that still point
at the recorded prefix target.

Older generated configs may contain removed `CLOUD_*` assignments; the bridge
ignores those inert values. External scripts using the removed token, CEF/CDP,
or pre/post Cloud options should migrate to `--cloud-native`.
