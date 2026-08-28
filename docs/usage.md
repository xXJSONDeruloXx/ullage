# Usage

Ullage edits one local Steam launch entry so the native macOS Steam Play
button invokes an external launcher. Steam must be fully quit while
`appcache/appinfo.vdf` is edited.

## Requirements

* Native macOS Steam configured to retain Windows depots. With Steam fully
  stopped, the machine interface can manage the bundled client setting:

  ~~~sh
  bin/ullagectl steam set-depot-mode windows --json
  ~~~

  Use `native` to remove the global Windows-depot directive. The setting is
  picked up after the next Steam restart.
* A prepared Wine prefix with `system.reg`. Use one prefix per AppID while the
  lifecycle and reaper work remains experimental.
* Wine and GPTK/D3DMetal matching the [runtime contract](../runtime/README.md).
  Fetch the verified lsteamclient package on a new machine with:

  ```sh
  bin/ullagectl runtime fetch --json
  ```
* Native Steam's `steamclient.dylib`.
* For 64-bit games, stage the verified forwarder into the selected prefix while
  native Steam is stopped:

  ```sh
  bin/ullagectl runtime stage-forwarder --prefix /path/to/prefix --json
  ```

## Build and check

~~~sh
make
make check
~~~

The opt-in installer transaction rehearsal requires native Steam to be fully
quit because it edits only a temporary appcache:

~~~sh
make integration
~~~

## Install the verified bridge package

The normal new-machine path is release-backed and one command:

~~~sh
bin/ullagectl runtime fetch --json
bin/ullagectl runtime verify --json
~~~

The pinned public release comes from
[`ullage-patches`](https://github.com/xXJSONDeruloXx/ullage-patches/releases).
For an offline or manually downloaded archive, `runtime install --manifest`
remains available and performs the same per-artifact verification.

Only the four small lsteamclient/forwarder artifacts are staged under
`~/.ullage/runtimes`. The exact tested GameHub host-runtime option is separate:

~~~sh
bin/ullagectl runtime host-releases --json
bin/ullagectl runtime host-fetch --json
bin/ullagectl runtime host-verify --json
~~~

That path downloads the clean GameHub Wine archive from its pinned GitHub
release and fetches the matching GPTK archive from the original locked source.
It does not require GameHub.app and does not include a private game prefix.
Pass `--gptk-archive PATH` to use an exact local GPTK archive. `doctor` reports
the package/host manifests and the exact remediation if a required artifact is
missing or changed.

## Machine-facing commands

For discovery, setup screens, and diagnostics, use the versioned JSON facade:

~~~sh
bin/ullagectl doctor --json
bin/ullagectl runtime list --json
bin/ullagectl library --json
bin/ullagectl plan APPID --json
bin/ullagectl smoke --json
bin/ullagectl steam set-depot-mode windows --json
bin/ullagectl metadata status APPID --json
bin/ullagectl metadata reconcile APPID --json
bin/ullagectl metadata reconcile APPID --restart-steam --json
~~~

The separate GUI should call `ullagectl` only. It should use the returned
runtime and launch-plan objects instead of learning GameHub paths or parsing
the output of the lower-level scripts. See the [CLI contract](cli.md) for
response fields, states, error codes, and mutation behavior.

Repeated checks should use `metadata reconcile` or `install --if-needed`.
Healthy mappings are returned as no-ops and do not require a Steam restart;
only a real stale metadata repair needs the Steam lifecycle boundary. Use
`--restart-steam` when Ullage should quit and relaunch Steam itself, verify
Steam Helper and the fresh AppInfo read, and return with native Play and Stop
ready.

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
directory. Windows options that cannot be mapped because their target is
missing, outside the depot, not a PE executable, or uses an unsupported path
are kept in the record with a private `ullage-disabled` marker so Steam does
not offer a broken native path. The original launch metadata is recorded and
restored by `ullage-remove`. Non-Windows options are left unchanged. Use
`--launch-entry KEY` when a title's launcher is not a direct Windows PE
executable or when only one option should be redirected; explicit entry mode
does not alter the other options.

Use these options only when needed:

* `--arch win32` or `--arch win64` overrides PE detection.
* `--wine-dllpath` supplies an alternate colon-separated Wine/D3D library path.
* `--steam-client-root` imports the user-owned Windows Steam client support
  files required by the selected architecture and records their hashes. This
  is not a download switch: Valve's payload is not redistributed by Ullage.
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

After installation, press Steam's ordinary Play button. With
`install --restart-steam`, Ullage performs the required Steam lifecycle and
waits for Steam Helper plus the fresh AppInfo read before returning; the
generated launcher then receives Steam's arguments. The bridge waits for the
exact Wine launcher, waits for the selected prefix's Wine session to become
idle, and then reaps only prefix-owned helpers.

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

Repair a stale mapping atomically. The explicit low-level path still requires
Steam to be fully quit:

~~~sh
"$HOME/Developer/ullage/bin/ullage-mapping.py" repair \
  --appid APPID \
  --steam-root "$HOME/Library/Application Support/Steam"
~~~

Repair backs up appinfo under `~/.ullage/backups/appinfo`, uses the recorded
entry as an optimistic concurrency check, and refuses to overwrite a foreign
mapping unless `--force` is explicit. It does not recreate missing runtime
state; reinstall or restore that state first. The `ullagectl repair APPID
--restart-steam` facade manages the quit, repair, relaunch, and AppInfo-read
verification as one operation.

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
