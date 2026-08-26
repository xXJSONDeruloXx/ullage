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

The installer changes only the Windows `.exe` launch entries in Steam's binary
`appinfo.vdf` whose executables are present in the installed depot. Each
available entry gets a small launcher outside the depot, so Steam's native
launch-option chooser can still select a different executable, argument list,
or working directory. Optional entries that are advertised in appinfo but are
not present in the installed depot are left native and are not made selectable
through Ullage. The target PEs are not renamed, wrapped, or overwritten, so
Steam can continue to verify the untouched depot. The launchers can be
regenerated from recorded state.

## Ownership

| Area | Owner |
| --- | --- |
| Windows depot selection and verification | native Steam |
| Play/Stop, AppID, session, playtime, and overlay | native Steam |
| Auto-Cloud transfer, badge, and conflict policy | native Steam |
| Local launch mapping and guarded cleanup | Ullage |
| Wine/GPTK process and prefix boundary | Ullage bridge |
| Windows API translation and Steamworks handoff | Wine/GPTK + lsteamclient |

Generated launchers, config, backups, prefixes, and logs are runtime state
under `~/.ullage` by default. The repository is source and provenance, not a
runtime data directory.

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
~/.ullage/                  launchers, configs, backups, prefixes, logs
Steam/appcache/appinfo.vdf  native Steam's local control-plane cache
~~~

## Source map

* `bin/ullage-install` / `bin/ullage-remove` — install and restore the launch
  mapping.
* `bin/ullage-mapping.py` — status and conservative repair.
* `bin/ullage-bridge` — hot launch and process supervision boundary.
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
Wine/Proton fork, or browser/token Cloud transport. Upstream-sensitive
Wine/Proton portability work belongs in
[ullage-patches](https://github.com/xXJSONDeruloXx/ullage-patches).
