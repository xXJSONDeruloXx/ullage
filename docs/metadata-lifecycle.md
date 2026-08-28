# Metadata lifecycle

Ullage's Steam metadata is deliberately treated as a guarded control-plane
transaction. The owned data is the AppID launch mapping and, when requested,
the native Cloud UFS override in Steam's binary `appcache/appinfo.vdf`.

## Operational contract

Inspecting or reconciling an already healthy mapping is a no-op and does not
require Steam to restart:

~~~sh
bin/ullagectl metadata status APPID --json
bin/ullagectl metadata reconcile APPID --json
bin/ullagectl install APPID --if-needed --json
~~~

The result reports `changed: false`, `restart_required: false`, and
`requires_steam_stopped: false` for this steady state. This is the normal
path for a UI or watchdog that checks metadata repeatedly.

When Steam has rewritten an Ullage-owned launch entry, reconciliation is
different. `metadata reconcile` creates a private backup, uses an optimistic
current-value check, writes a temporary binary VDF, fsyncs it, and atomically
replaces `appinfo.vdf`. It refuses to write while native Steam is running and
returns the stable `steam_running` error instead. After a successful change,
`restart_required: true` remains explicit: the next Steam start is needed for
the client to discard its cached appinfo record. A stale mapping is never
silently edited underneath a live Steam client.

`repair` follows the same policy. A healthy mapping now succeeds as an
idempotent no-op even when Steam is open; only an actual stale repair is
blocked by the stopped-Steam guard. `remove` remains destructive and always
requires Steam to be stopped.

## Why there is no live appinfo write path

On 2026-08-28, a bounded experiment backed up the live AppInfo file, changed
only AppID `2492670` entry `0`, and launched
`steam://rungameid/2492670` without restarting Steam. The file was restored
byte-for-byte afterward (SHA-256
`a28636c814e2d4857afdc940b5a1c4eb6c9c4da4c871328892871ff7856c6688`). The
launch produced a bridge process, but the run was not a clean proof of a live
metadata refresh: Steam provided no reload acknowledgement, the observed
session exited with Wine status `53`, and the running client retained its own
cached state. Therefore Ullage does not claim that an atomic file replacement
is a supported hot reload protocol.

The practical zero-restart behavior comes from idempotence and persistence:
install the mapping once, leave the generated launcher in place, and do not
rewrite appinfo on every launch or status check. A restart is reserved for a
real client-cache repair or a deliberate install/remove transaction.

## Recovery

If a metadata operation reports `steam_running`, leave the files untouched,
gracefully quit native Steam, run the same reconcile command again, then
restart Steam once if the result reports `restart_required`. Backups are kept
under `~/.ullage/backups/appinfo` and the mapping state records the original
launch values, so a failed transaction can be rolled back without touching the
installed game executable.
