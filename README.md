# Ullage

Ullage is the empty headspace between wine and its container: the gap between
Steam and Wine on macOS.

It is a small launch-boundary bridge for untouched Windows Steam depots on
native macOS Steam. Steam remains the control plane for downloads, Play/Stop,
AppID and session state, Steamworks transport, overlay, and Cloud. Ullage
supplies the missing boundary that starts the Windows executable in a prepared
Wine/GPTK runtime.

Ullage is not a replacement Steam client, compatibility manager, UI injection
layer, Wine fork, or runtime distribution.

## Architecture

~~~text
native macOS Steam
        |
        | ordinary Play action
        v
local appinfo launch mapping
        |
        v
ullage-bridge -> Wine/GPTK + lsteamclient -> Windows PE game
        ^                                      |
        +---------- native Steam session ------+
~~~

The game depot remains untouched. Generated launch state and runtime data live
under `~/.ullage`; the repository contains the bridge and its tests.

## Status

The native launch boundary, Steam Stop cleanup, Steamworks transport, and
known Windows Auto-Cloud root mappings are implemented and tested on macOS.
This remains an experimental compatibility boundary, not a claim that every
Windows game or renderer works.

The current host uses Steam's global
`@sSteamCmdForcePlatformType windows` setting to obtain Windows depots. Native
Cloud remains Steam-owned; Ullage does not fake the Cloud badge or implement a
second transfer service.

## Start here

Read [Usage](docs/usage.md) for prerequisites and commands. Run the local
checks with:

~~~sh
make check
~~~

## Documentation

* [Usage](docs/usage.md) — prerequisites, installation, repair, removal, and
  lifecycle behavior.
* [Architecture](docs/architecture.md) — ownership boundaries, state layout,
  source map, and design constraints.
* [Native saves](docs/native-saves.md) — supported roots, live evidence, and
  remaining Cloud TODOs.
* [Platform selection](docs/platform-selection.md) — the per-AppID depot
  investigation and the current global-setting boundary.
* [Compatibility-tool boundary](docs/compatibility-tool-research.md) — the
  native macOS dispatch experiment and reconsideration gate.
* [Steamworks acceptance](docs/steamworks-acceptance.md) — real-game matrix,
  probes, and known compatibility boundaries.
* [Runtime contract](runtime/README.md) — host-supplied Wine/GPTK and
  lsteamclient requirements.
* [macOS onboarding log](docs/macos-onboarding.md) — first-machine setup
  evidence, road bumps, and the remaining end-to-end test gaps.

Upstream-sensitive Wine/Proton portability work belongs in
[ullage-patches](https://github.com/xXJSONDeruloXx/ullage-patches), not in this
small Steam launch bridge.
