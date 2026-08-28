# Machine interface

`bin/ullagectl` is Ullage's stable machine-facing boundary. It is a thin
facade over the existing launch, mapping, Cloud, and bridge tools. A GUI or
other caller should use this command rather than invoking those implementation
scripts independently.

## Contract

Every successful or handled failure writes one JSON object to stdout with:

~~~json
{
  "api_version": 1,
  "command": "library",
  "ok": true
}
~~~

The process exits zero for `ok: true` and nonzero for `ok: false`. Errors have
stable `code` and `recoverable` fields; the human-readable `message` may
change:

~~~json
{
  "api_version": 1,
  "command": "install",
  "ok": false,
  "error": {
    "code": "steam_running",
    "message": "Native Steam must be fully quit before installing a mapping.",
    "recoverable": true
  }
}
~~~

`--json` is accepted explicitly for clarity and is currently a no-op because
the facade always speaks this JSON protocol. Human-oriented helper output is
never part of the GUI contract.

## Commands

Read-only commands:

~~~sh
bin/ullagectl capabilities --json
bin/ullagectl doctor --json
bin/ullagectl runtime list --json
bin/ullagectl runtime verify --json
bin/ullagectl library --json
bin/ullagectl inspect APPID --json
bin/ullagectl diagnose APPID --json
bin/ullagectl plan APPID --json
bin/ullagectl smoke --json
bin/ullagectl runtime releases --json
bin/ullagectl runtime host-releases --json
bin/ullagectl runtime host-verify --json
~~~

`system-status`, `status`, and `discover` remain accepted aliases for
compatibility. AppIDs may also be supplied as `--appid APPID`.

`library` returns installed Steam games, Windows launch options, mapping state,
native Cloud support, and discovered runtimes. It also returns
`not_installed`, a catalog of game/application records with Windows launch
metadata present in Steam's local AppInfo cache but no installed manifest.
AppInfo is intentionally used here because it is available to a packaged GUI
without walking privacy-protected account directories; cached entries are not
an ownership proof. The GUI should use the search and filter controls when the
cache is large. Installed game records also include `launch_parameters`, the
persisted compatibility values consumed by the generated launcher. This
includes the Wine environment knobs (`wine_debug`, `winemsync`, `wine_dllpath`,
and `wine_dll_overrides`), launch selection, prefix/architecture, Steam
transport, legacy/client-runtime paths, logging, and native Cloud overrides. A
GUI should round-trip this object through `install` rather than parse the
generated shell config. Game state is one of:

* `not_installed` — a Windows-capable cached game is not installed locally.
* `ready` — the recorded Ullage mapping is intact and at least one Windows PE
  launch option is usable.
* `available` — a Windows PE launch option is present and can be prepared.
* `stale` — Steam rewrote a recorded mapping.
* `broken` — generated state or a previously usable target is incomplete.
* `unsupported` — no usable Windows PE launch option is available.
* `native` — only an untouched native macOS launch is available.

`plan` is read-only. It returns the exact launch entries that will be mapped or
disabled, the native Cloud action, the selected runtime, and any blocking
issues. It is the source for a Configure screen; the GUI must not reimplement
multi-launch or Cloud rules.

`smoke` is a read-only two-title bridge preflight. By default it checks the
known-good 32-bit TIS-100 control (`370360`) and the known x64 forwarder
control (`848350`, Katamari Damacy REROLL). Pass an AppID positionally and
`--x64-appid` to use different matrix controls. Both titles must already be
installed and mapped; the command does not press Play or synthesize a native
Steam Stop event. Its JSON includes the exact `steam://rungameid/` URLs and
the native Play/Stop acceptance steps.

Mutating commands are:

~~~sh
bin/ullagectl install APPID --runtime RUNTIME_ID --json
bin/ullagectl repair APPID --json
bin/ullagectl repair APPID --restart-steam --json
bin/ullagectl remove APPID --json
bin/ullagectl metadata status APPID --json
bin/ullagectl metadata reconcile APPID --json
bin/ullagectl metadata reconcile APPID --restart-steam --json
bin/ullagectl runtime fetch --json
bin/ullagectl runtime host-fetch --json
bin/ullagectl runtime rollback --json
bin/ullagectl runtime stage-forwarder --prefix PREFIX --json
~~~

`install` can resolve the target, Steam install directory, and GameHub runtime
paths from discovery. An initialized prefix is still required; callers may
override it with `--prefix`. Explicit `--target`, `--install-dir`,
`--wine-root`, `--gptk-root`, and `--bridge-root` remain supported for
non-GameHub providers and reproducible tests. Re-running it for a healthy
Ullage mapping is the supported way to apply a different runtime profile; the
facade permits replacement only after confirming that the existing mapping is
healthy. Stale or foreign mappings remain guarded.

Use `install --if-needed` when a caller is checking or ensuring an existing
mapping. It returns a successful no-op for a healthy mapping, even while Steam
is running, so routine UI refreshes do not cause metadata writes or Steam
restarts. `metadata status` and `metadata reconcile` expose the same policy
explicitly. Reconcile repairs only stale Ullage-owned state, refuses to write
under a live Steam client, and reports `restart_required` after a successful
write because Steam caches AppInfo in memory. The `--restart-steam` option
turns this into a managed transaction: Ullage quits Steam safely, writes the
mapping, relaunches Steam, and waits for Steam Helper and a fresh AppInfo
read. The returned `steam_session.started.ready` field is the readiness signal
for a GUI to enable ordinary Play and Stop actions. `install --restart-steam`
uses the same lifecycle for a first mapping install, so a newly configured
title returns with the native Steam controls ready.

The `capabilities` response includes `steam_session_management` when this
managed lifecycle is available.

All mutations enforce the same invariant as the lower-level tools: native
Steam must be fully stopped while `appcache/appinfo.vdf` is changed. The GUI
may request a graceful quit and relaunch, but Ullage remains the final guard.

The Steam depot setting is also a core mutation:

~~~sh
bin/ullagectl steam set-depot-mode windows --json
bin/ullagectl steam set-depot-mode native --json
~~~

It edits only the bundled macOS Steam `steam_dev.cfg` (or the equivalent
`--steam-root` candidate), preserves unrelated lines, writes atomically, and
refuses to run while native Steam is present. `windows` writes exactly one
`@sSteamCmdForcePlatformType windows` directive; `native` removes it. The
configuration takes effect after Steam restarts.

## Runtime objects

`runtime list` and the `runtimes` field in `library` expose provider details
needed by a UI without exposing provider-specific conventions:

~~~json
{
  "id": "gamehub-container-2",
  "name": "gamehub-2",
  "provider": "gamehub",
  "status": "ready",
  "wine_root": "...",
  "gptk_root": "...",
  "prefix": "...",
  "prefix_base": "...",
  "sandboxfs": true,
  "supports": ["win32", "win64"]
}
~~~

The object also contains checks and optional SandboxFS paths when GameHub has
them. A future provider can implement the same object without changing the
GUI.

`runtime list` also returns `packages`, `current_package`, `host_runtimes`, and
`current_host_runtime`. A bridge package is the small, versioned lsteamclient
bridge staged by Ullage. A host runtime is a separate versioned Wine/GPTK
installation with a clean prefix. Native Steam, account-bearing prefixes, and
GameHub's proprietary SandboxFS remain outside both public release boundaries.
Install and verify a bridge package with:

~~~sh
bin/ullagectl runtime install --manifest PATH/manifest.json --json
bin/ullagectl runtime verify --json
bin/ullagectl runtime verify --runtime-id ID --version VERSION --json
~~~

`runtime install` verifies every manifest digest and size before staging. The
copy is verified again before `current.json` is atomically updated. The
package object exposes `runtime_id`, `version`, `manifest_sha256`,
`bridge_root`, per-artifact status, and source provenance. A failed
verification names the manifest or artifact that needs to be replaced.

`runtime releases` exposes the checked-in release lock. `runtime fetch` downloads
the default pinned public release directly over HTTPS, verifies its byte count
and SHA-256, rejects unsafe tar members, verifies the extracted manifest and
every artifact, and only then installs the package. The archive is cached under
`~/.ullage/downloads` by default; `--cache-dir` can place it on another volume.
The release lock is in `runtime/releases.json` and must be updated together
with a release asset and its digest.

`runtime host-releases` exposes the pinned host-runtime lock. `runtime host-fetch`
downloads and verifies the exact GameHub Wine archive from the tagged GitHub
release, then obtains the exact GPTK archive from its locked original source
URL (or accepts an exact local archive through `--gptk-archive`). It atomically
installs both under `~/.ullage/host-runtimes`. `runtime host-verify` validates
the active host manifest, required Wine/GPTK paths, and extracted symlink
layout. This path does not require GameHub.app to be installed.

The Windows Steam client DLLs are a separate, user-owned input because Valve's
payload is not an Ullage-redistributable artifact. Supply the root containing
the Windows Steam client files when installing a mapping:

~~~sh
bin/ullagectl install APPID \
  --steam-client-root "/path/to/Steam/drive_c/Program Files (x86)/Steam" \
  --steamclient64-forwarder stock
~~~

For `win64`, Ullage hashes and stages `steamclient64.dll`, `tier0_s64.dll`,
and `vstdlib_s64.dll`; for `win32`, it stages the corresponding legacy set.
The source path, architecture, sizes, and SHA-256 values are recorded in
`~/.ullage/config/games/APPID.steam-client.json`. Existing mismatched prefix
files are preserved as timestamped `.ullage-original-*` backups. The staged
files are then independent of GameHub's cache or application at launch.

`runtime rollback` atomically switches `current.json` to the previous verified
package, or to the package named by `--runtime-id` and `--version`. Packages
are never deleted, and the previous pointers are retained in
`runtimes/history.json`. For an x64 title, `runtime stage-forwarder --prefix`
copies the verified canonical-name forwarder into the prefix with an atomic
replace and saves an existing prefix file as `steamclient64.dll.ullage-original`.
`runtime restore-forwarder` restores that saved file. Both prefix operations
require native Steam to be stopped.

## Diagnostics

After a bridge run, Ullage writes a structured receipt at
`~/.ullage/sessions/APPID/last.json`. `inspect` and `diagnose` expose that
receipt along with residual-process checks and a log path. The receipt records
the AppID, entry, architecture, runtime, native Stop and native Steam-client
exit observations, Wine exit, signal, reaped helper/game counts, and prefix
cleanliness. The text log remains for human debugging; callers should use the
receipt fields.

The facade deliberately does not expose the optional Steamworks probe as a
green compatibility verdict until its ABI declarations and JSON output are
made safe for that purpose.

`doctor` includes `blocking_checks` and ordered `next_steps`. Each step names
the missing host input, the remediation text, and a command where Ullage can
perform the fix. Wine, GPTK/D3DMetal, native Steam, the Windows depot, and an
initialized prefix remain host responsibilities; `runtime fetch` only closes
the bridge-package gap.
