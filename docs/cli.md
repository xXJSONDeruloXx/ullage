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
bin/ullagectl library --json
bin/ullagectl inspect APPID --json
bin/ullagectl diagnose APPID --json
bin/ullagectl plan APPID --json
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
cache is large. Game state is one of:

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

Mutating commands are:

~~~sh
bin/ullagectl install APPID --runtime RUNTIME_ID --json
bin/ullagectl repair APPID --json
bin/ullagectl remove APPID --json
~~~

`install` can resolve the target, Steam install directory, and GameHub runtime
paths from discovery. An initialized prefix is still required; callers may
override it with `--prefix`. Explicit `--target`, `--install-dir`,
`--wine-root`, `--gptk-root`, and `--bridge-root` remain supported for
non-GameHub providers and reproducible tests. Re-running it for a healthy
Ullage mapping is the supported way to apply a different runtime profile; the
facade permits replacement only after confirming that the existing mapping is
healthy. Stale or foreign mappings remain guarded.

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

## Diagnostics

After a bridge run, Ullage writes a structured receipt at
`~/.ullage/sessions/APPID/last.json`. `inspect` and `diagnose` expose that
receipt along with residual-process checks and a log path. The receipt records
the AppID, entry, architecture, runtime, stop observation, Wine exit, signal,
reaped helper/game counts, and prefix cleanliness. The text log remains for
human debugging; callers should use the receipt fields.

The facade deliberately does not expose the optional Steamworks probe as a
green compatibility verdict until its ABI declarations and JSON output are
made safe for that purpose.
