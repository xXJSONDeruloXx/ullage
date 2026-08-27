# Architecture

Ullage keeps native macOS Steam as the control plane and adds only the missing
execution boundary.

## Launch boundary

~~~text
native macOS Steam
        |
        | AppID, arguments, environment, Steam IPC
        v
local appcache launch mapping
        |
        | external launcher outside the depot
        v
ullage-bridge
        |
        | explicit environment and prefix-scoped supervision
        v
Wine/GPTK + D3DMetal
        |
        | lsteamclient.dll + lsteamclient.so
        v
Windows PE game -> native Steam client/session/overlay
~~~

The installer changes only the Windows launch entries in Steam's binary
`appinfo.vdf` whose executables are present in the installed depot as Windows
PEs. Each available entry gets a small launcher outside the depot, so Steam's
native launch-option chooser can still select a different executable, argument
list, or working directory. Windows entries that cannot be mapped are retained
with a private `ullage-disabled` marker and exact restore metadata rather than
being exposed as broken native paths. Non-Windows entries remain untouched.
The target PEs are not renamed, wrapped, or overwritten, so Steam can continue
to verify the untouched depot. The launchers and disabled-option state can be
regenerated from recorded state.

## Ownership

| Area | Owner |
| --- | --- |
| Windows depot selection and verification | native Steam |
| Guarded depot-mode configuration | Ullage CLI; native Steam applies it |
| Play/Stop, AppID, session, playtime, and overlay | native Steam |
| Auto-Cloud transfer, badge, and conflict policy | native Steam |
| Local launch mapping and guarded cleanup | Ullage |
| Wine/GPTK process and prefix boundary | Ullage bridge |
| Windows API translation and Steamworks handoff | Wine/GPTK + lsteamclient |
| Versioned bridge artifact verification and staging | Ullage runtime package layer |
| Versioned Wine/GPTK host option and clean-prefix layout | Ullage host-runtime package layer |

Generated launchers, config, backups, prefixes, and logs are runtime state
under `~/.ullage` by default. The repository is source and provenance, not a
runtime data directory.

The optional release-installed host runtime is separate state under
`~/.ullage/host-runtimes`. It carries the exact clean GameHub Wine payload and
the user-sourced matching GPTK payload, but never native Steam, GameHub's
SandboxFS library, or an account-bearing per-game prefix. A source-built Wine
provider can implement the same profile contract without changing the GUI.

The machine-facing boundary is `bin/ullagectl`. It is a thin JSON facade over
the existing helpers: it discovers GameHub runtimes, installed depots, and
cached not-installed Windows-capable catalog entries, builds read-only install
plans, delegates guarded mutations, and translates
helper failures into stable error codes. A separate UI may depend on this
facade, but it must not reproduce Steam, GameHub, AppInfo, or mapping logic.

## Lifecycle

The bridge supervises the exact Wine launcher, then waits for the selected
prefix's Wine session to become idle before reaping prefix-owned helpers. It
does not perform a global process-name kill.

Because native macOS Steam records an external launcher but does not signal it
directly on Stop, the bridge watches the active AppID's `Terminating` event in
Steam's content log. It sends the normal signal through the supervisor and
uses the same bounded prefix cleanup path. This keeps Stop in the native Steam
UI without UI injection.

The boundary preserves Steam's native AppID and user/session context, loader,
overlay environment, inherited Steam IPC descriptors when enabled, virtual
gamepad metadata, depot verification surface, and process lifecycle. Cleanup
is bounded to the selected prefix and never uses a global process-name kill.

## State and recovery

Steam may rewrite `appcache/appinfo.vdf` during metadata refreshes or client
updates. Ullage treats the mapping as local and repeatable: install records a
private backup, status detects stale or foreign state, repair uses an optimistic
concurrency check, and remove restores the recorded native entry.

The state root is separate from the checkout:

~~~text
repository/                 source, tests, runtime contract
~/.ullage/                  launchers, configs, backups, prefixes, logs,
                            sessions/<appid>/last.json receipts,
                            runtimes/<id>/<version>/ verified bridge packages,
                            runtimes/current.json active package pointer,
                            runtimes/history.json rollback pointers,
                            downloads/ verified release archives
Steam/appcache/appinfo.vdf  native Steam's local control-plane cache
~~~

## Source map

* `bin/ullage-install` / `bin/ullage-remove` — install and restore the launch
  mapping.
* `bin/ullagectl` / `bin/ullage` — versioned JSON discovery, planning, and
  mutation facade for machine callers.
* `bin/ullage-mapping.py` — status and conservative repair.
* `bin/ullage-bridge` — hot launch and process supervision boundary.
* `bin/ullage-runtime.py` — release/archive/manifest verification, package
  staging, rollback, forwarder staging, and runtime provenance.
* `bin/ullage-reap` — prefix-scoped cleanup.
* `bin/ullage-appinfo.py` — dependency-free binary VDF editing.
* `bin/ullage-path.py` — install-root-relative launcher path calculation.
* `bin/ullage-cloud-path.py` / `bin/ullage-cloud-native.py` — native Cloud root
  mapping and guarded links.
* `bin/ullage-fd-exec` / `src/ullage-fd-exec.c` — descriptor-boundary helper.
* `tools/ullage-steamworks-probe.c` — optional direct Steamworks diagnostic.

The [Steamworks acceptance matrix](steamworks-acceptance.md) records observed
behavior rather than treating a successful Play click as universal support.
The [native-save ledger](native-saves.md) records Cloud-specific evidence and
remaining gaps.

## Deliberate non-goals

Ullage does not become a replacement Steam client, compatibility manager, GUI,
Wine/Proton fork, full runtime distribution, or browser/token Cloud transport.
Its optional package is limited to the small bridge artifacts needed at the
launch boundary. Upstream-sensitive
Wine/Proton portability work belongs in
[ullage-patches](https://github.com/xXJSONDeruloXx/ullage-patches).
