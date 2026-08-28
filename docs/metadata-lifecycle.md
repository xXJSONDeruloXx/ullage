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
replaces `appinfo.vdf`. On this native macOS Steam client, AppInfo is cached in
memory, so there is no supported true hot-reload path for a stale entry. By
default it refuses to write while Steam is running and returns the stable
`steam_running` error instead.

For an end-user operation that may manage the client lifecycle, pass
`--restart-steam`:

~~~sh
bin/ullagectl metadata reconcile APPID --restart-steam --json
bin/ullagectl repair APPID --restart-steam --json
bin/ullagectl install APPID --restart-steam --json
~~~

Ullage then refuses to interrupt an active Ullage bridge session, gracefully
asks Steam to quit, waits for all Steam processes to exit, performs the
transaction, starts Steam again, and waits for Steam Helper plus a fresh
AppInfo cache read. A successful managed operation reports
`steam_session.started.ready: true`, `mapping_status: healthy`, and
`restart_required: false`; Play and Stop are ready for the caller. If the
flag is omitted, a successful stale repair reports `restart_required: true`
because the caller still owns the next Steam start.

`repair` follows the same policy. A healthy mapping now succeeds as an
idempotent no-op even when Steam is open; only an actual stale repair needs the
stopped-Steam guard or the managed `--restart-steam` flow. `remove` remains
destructive and always requires Steam to be stopped.

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
real client-cache repair or a deliberate install/remove transaction, and the
managed form makes that exceptional lifecycle automatic and verified.

## Recovery

If a metadata operation reports `steam_running`, leave the files untouched and
retry with `--restart-steam` after confirming no game is active. Backups are
kept under `~/.ullage/backups/appinfo` and the mapping state records the
original launch values, so a failed transaction can be rolled back without
touching the installed game executable.
