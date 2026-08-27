# macOS onboarding log

This is a running record of first-machine setup friction and observed
requirements for Ullage. It is intentionally host-specific where paths or
runtime behavior are involved. The project remains responsible for the small
launch bridge; Wine, GPTK/D3DMetal, lsteamclient, and native Steam remain
host-provided components.

## Snapshot: 2026-08-26

Repositories were fast-forwarded from `origin/main` before this test:

* Ullage: `7113b2f` (`test: record SLUDGE LIFE renderer coverage`)
* ullage-patches: `daf9591` (`runtime: add x64 Steam client forwarder`)

The test host is an Apple M1 Mac mini with 8 GB RAM, macOS 15.6.1, Rosetta 2,
native Steam build `1785799196`, and about 20 GB free on the internal Steam
library after the test install. Rosetta can execute the x86_64 Wine runtime.

## Road bumps

### 1. The Windows depot flag needs the macOS client path

The setting itself is:

```text
@sSteamCmdForcePlatformType windows
```

On macOS Steam, the file must be:

```text
$HOME/Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/MacOS/steam_dev.cfg
```

Putting the same line in the Steam data root,
`$HOME/Library/Application Support/Steam/steam_dev.cfg`, was silently
ineffective. A reinstall then mounted the macOS depot: an `.app` bundle and
about 92 MB for TIS-100. Moving the line to the bundled client's
`Contents/MacOS` directory and fully restarting Steam mounted the Windows
depot instead: depot `370361`, 50,190,783 bytes, with
`tis100.exe` identified as a PE32 Windows executable.

The restart is required before the setting affects content selection. The
normal native Steam Play action still cannot execute that Windows executable;
without an Ullage mapping it returned `Failed to start process for this game:
OS Error 0`.

### 2. Steam's usable Computer Use target is the CEF helper

The reliable target on this host is:

```text
$HOME/Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/Frameworks/Steam Helper.app
```

The parent targets (`Steam`, `com.valvesoftware.steam`, `/Applications/Steam.app`,
and the alternate parent bundle) can fail with a ScreenCaptureKit `-10005`
capture error or duplicate-bundle resolution. The helper reports the real
Steam window and screenshot.

Its accessibility tree exposes only the standard window and `Raise`; CEF page
controls are not usable accessibility elements. The reliable workflow is:

1. Capture a fresh helper screenshot.
2. Derive coordinates from that screenshot.
3. Perform one coordinate action.
4. Capture a new screenshot and derive coordinates again.

Store navigation, Library search, text entry, Return, product selection, and
the TIS-100 install/uninstall controls were exercised this way. No CEF remote
debugging port is needed.

The helper can be relaunched through Computer Use once the parent is running,
but Computer Use could not cold-launch or fully quit the parent on this host.
The standard macOS launcher was needed to start `/Applications/Steam.app`,
and the exact verified `steam_osx` process had to be terminated to force a
client restart. This is an operational setup concern, not an Ullage runtime
requirement.

### 3. A fresh checkout may need `make` before live bridge validation

`make check` passed, including the shell and Python tests, but the `check`
target does not depend on `all`. On a clean host the generated
`bin/ullage-fd-exec` helper may therefore be absent even though the test suite
is green. Running `make` first produced the universal helper and allowed the
bridge preflight to reach its runtime checks.

The Steamworks probe was skipped because MinGW was not available. That is a
known test-environment gap, not a failure of the other checks.

### 4. GameHub's Wine runtime is not a drop-in raw `wine` command

GameHub supplied these useful components:

* Wine Proton 11.0, x86_64, at
  `$HOME/Library/Application Support/com.gamemac.www/wine-engine/containers/wine_installations/10000073`
* Apple GPTK 3.0-3 at
  `$HOME/Library/Application Support/com.gamemac.www/wine-engine/downloads/gptk-3.0-3`
* An initialized GameHub virtual prefix at
  `$HOME/Library/Application Support/com.gamemac.www/wine-engine/containers/virtual_containers/1`

The installation's own `prefix` directory is not the same thing as the
GameHub game prefix. GameHub's recorded launch environment includes
`WINE_PATH`, `WINE_INSTALLATION_PATH`, `WINEPREFIX`, `WINEPREFIX_BASE`,
`WINEDLLPATH`, `DYLD_FALLBACK_LIBRARY_PATH`,
`WINE_GPTK_LIBD3DSHARED_PATH`, `WINEARCH`, and GameHub's monitor/sandbox
handoff variables. Invoking `bin/wine` with only a prefix failed to load
`kernel32.dll`. Replaying the recorded environment reached Wine/MSYNC, but a
raw TIS-100 invocation exited with status 53 without opening a window. This
does not establish a renderer failure; it shows that the supported GameHub
container launch contract still needs to be reproduced or deliberately
formalized for Ullage.

### 5. GameHub did not supply Ullage's Steam transport bridge

The Wine and GPTK artifacts are present and usable as host inputs, but no
matching files were found under the GameHub data root for:

```text
x86_64-unix/lsteamclient.so
i386-windows/lsteamclient.dll
x86_64-windows/lsteamclient.dll
```

The native Steam `steamclient.dylib` is present separately. The unrelated
Android `libsteamclient.so` found elsewhere is not a substitute.

`ullage-patches` records the required source patch and the x64
`steamclient64.dll` forwarder, but it deliberately does not vendor the Wine
source or generated lsteamclient outputs. Its build script expects a clean
patched Wine/Proton source tree and `x86_64-w64-mingw32-gcc`; that compiler is
also absent on this host. Ullage's read-only bridge preflight stopped at:

```text
required file is missing: .../ullage/runtime/lsteamclient/x86_64-unix/lsteamclient.so
```

At this stage of the initial setup this was the hard blocker for an
end-to-end Steam Play test. The later remediation below produced the missing
host Unix/i386 pair and the x64 forwarder; the current validation record is in
section 11.

## Test record

During the initial onboarding pass, TIS-100 (AppID `370360`) was already owned
and was selected as the small test title. The native Steam client was restarted
with the correctly placed depot flag, the Windows depot was downloaded to the
internal library, and the installed files were verified without modifying the
depot contents. The native Play attempt and Ullage bridge preflight were then
allowed to fail at their respective documented boundaries. No Ullage appinfo
mapping was installed at that time because the required bridge artifacts were
absent.

The Windows depot remains installed at:

```text
$HOME/Library/Application Support/Steam/steamapps/common/TIS-100
```

## Prerequisites identified before the first full Ullage run

These were the outstanding requirements before the source-backed runtime
remediation. Sections 6 through 8 record how the disposable build and
GameHub-compatible launch contract closed them.

1. A clean, pinned Wine/Proton source checkout containing the matching
   `dlls/lsteamclient` source.
2. The `ullage-patches` portability patch applied and verified against that
   checkout.
3. Built bridge outputs for the selected architecture: the Unix
   `lsteamclient.so` plus the Windows lsteamclient DLL. Add the x64 Windows
   DLL and build/stage the canonical-name forwarder for win64 titles.
4. A reproducible way to create or clone one initialized GameHub-compatible
   prefix per AppID, including the forwarder staging location for x64.
5. Enough disk headroom for the source checkout and build products; the
   current small-title test is fine, but a Wine rebuild on an 8 GB host with
   roughly 20 GB free is tight.
6. A documented launch environment that either uses GameHub's container
   handoff or supplies Ullage with equivalent Wine/GPTK loader variables.

Once those inputs exist, the next low-risk acceptance run is to install TIS-100
through `ullage-install`, restart native Steam, press Play through the helper,
and verify Wine launch, Steamworks initialization, native Stop, and clean
prefix-scoped reaping.

### 6. Remediation: fetch the matching Proton source instead of using an unrelated runtime

The missing bridge source was resolved by cloning Proton's `proton_11.0`
branch into the disposable work area and initializing its Wine submodule at
the exact pinned commit from `ullage-patches`:

```text
/Users/danhimebauch/Developer/ullage-runtime-work/proton-11
Wine: dc26e61847081a1b5cb0733dc30feba6ee575482
```

The sparse checkout includes Proton's top-level `lsteamclient/` source, and
the `ullage-patches` macOS portability patch applied cleanly to the Wine
submodule. This confirms that the source provenance is compatible; it does
not yet produce usable runtime binaries. The next step is a scoped Proton SDK
container build of the lsteamclient modules. The first build attempt should
watch disk usage because the host has only about 17 GB free.

The first invocation of Proton's `configure.sh` exposed another host
prerequisite: macOS `/bin/bash` is Bash 3.2, but this script uses Bash 4-style
case conversion (`${name,,}`). The configure step therefore stopped before it
could create a Makefile. A newer Homebrew Bash is needed for this build path;
the native Ullage scripts themselves still pass `make check` without it.

After installing Homebrew Bash 5, configure pulled the Proton SteamRT SDK
image successfully, but its UID probe treated Docker Desktop's default
Apple-Silicon warning (the image is `linux/amd64` on this ARM host) as the
numeric UID and stopped. The retry needs
`--docker-opts='--platform=linux/amd64'` so the probe sees a clean value. The
SDK image is build infrastructure only; a full Proton distribution build is
not part of this test.

That option is applied only to the generated Makefile and not to
`configure.sh`'s initial probe, so it did not fix the first retry. Setting
Docker's process-level `DOCKER_DEFAULT_PLATFORM=linux/amd64` is the effective
workaround for the probe on this ARM Mac.

The first direct Winemaker compile then failed because generated makefiles
split the GameHub runtime's absolute path at the spaces in `Application
Support`. The runtime itself is fine. The disposable build uses a no-space
symlink to the same installation and regenerates the makefiles through that
path; Ullage should eventually normalize or quote discovered runtime paths
before emitting build or launch commands.

With the path normalized, compilation reached the source and stopped because
GameHub's installed public headers omit Wine's internal `wine/list.h`. Adding
the pinned Wine checkout's `include/` directory as a disposable compile-only
include path supplies that header and keeps the GameHub runtime binaries
unchanged.

The next compile failure was a missing `TRACE`/`ERR` macro, not a missing
function: Wine's public debug header only defines those short names under
`__WINESRC__`, which Proton normally supplies from its Wine build flags. The
standalone module build now supplies that define explicitly.

The x64 module then hit Wine's PE-versus-Unix Winsock header collision:
`steamclient_main.c` includes C runtime headers before Winsock, so macOS
expands Darwin's `htonl`/`htons` macros into the Wine declarations. The exact
`__WINE_USE_MSVCRT` retry was incompatible with relocated native `winegcc`
because Wine's variadic debug helpers became Microsoft-ABI functions. The
disposable compile instead uses Wine's own `USE_WS_PREFIX` header mode and
keeps the ABI mode unchanged.

A complete direct Winemaker pass compiled most generated wrapper objects, but
failed at the `lsteamclient64.spec` dependency and at Unix-source compilation:
Proton's `unixlib.cpp`/`unixlib_generated.cpp` are meant to be built as Wine
Unix-library sources, with `WINE_UNIX_LIB` and the generated internal call-table
ABI. Treating every source as one Winelib target is therefore not a valid
standalone build recipe. The build was abandoned without using its partial
output.

The native Wine module path required Homebrew `autoconf`, Homebrew `bison`
(the system bison was too old), and Homebrew `mingw-w64`: Wine's native
configure rejected Apple Clang as a PE compiler because it lacks `-mabi=ms`.
With MinGW installed, the staged Wine configure now reaches the expected
x86_64 PE/Unix checks, but its generated makefile pass stops on the sparse
checkout's missing generated `wine/vulkan.h` even with `--without-vulkan`.
That is a build-system completeness issue, not evidence that TIS-100 needs
Vulkan; the next attempt will keep the source/build tree disposable and limit
configuration to the lsteamclient module inputs.

After generating the omitted Vulkan and syscall inputs, Wine configure completed
and emitted the real lsteamclient module rules. The first native compile still
failed because Apple Silicon's clang retained ARM preprocessor definitions when
the generated rule supplied only `-m64`; Wine then saw ARM64 and AMD64 context
types in the same header. The retry must pass an explicit `-arch x86_64` to the
host C and C++ compilers. This is another macOS cross-architecture build flag,
not a requirement to rebuild the full Proton runtime.

That retry compiled the C++ wrapper set, then stopped in `unixlib.cpp` because
Wine's Windows headers define the short `max` macro over C++'s `std::max`.
The host-only compile needs the usual `NOMINMAX` define; the successful object
files are retained in the disposable build directory for the next retry.

With the x86_64 compiler flag and `NOMINMAX`, all 219 native wrapper objects
compiled. A direct macOS link initially rejected the bridge's unresolved
Windows-facing symbols; adding `-undefined dynamic_lookup` matches Wine's
normal module-loading model, while the installed GameHub `x86_64-unix/ntdll.so`
remains the explicit native dependency. The resulting `lsteamclient.so` is an
x86_64 Mach-O dylib; it is not staged into Ullage until the matching PE side is
also available.

The first x86_64 PE link attempt compiled the wrapper objects but stopped before
linking because the generated dependency list pointed at
`wine-tools/tools/winegcc/wineg++`, while the disposable tool shim only exposed
`winegcc`. The GameHub installation does provide `wineg++` as a symlink to
`winegcc`; the retry adds that exact sibling symlink to the disposable tool shim.
This is a build-shim completeness issue, and does not require a full Proton
build.

To add the 32-bit PE target without rebuilding Proton, a second Wine configure
was started with `--enable-archs=i386,x86_64`. It reached the host and MinGW
compiler checks, then stopped on an unrelated missing macOS FreeType development
library. The scoped retry will disable FreeType (and other unused host features)
while retaining the i386 PE compiler; this is another configure-time dependency,
not a TIS-100 runtime requirement.

The first full new-machine matrix reproduction used Peggle Deluxe (AppID 3480),
which the checked-in acceptance matrix records as a known-good 32-bit control.
Steam downloaded the Windows depot and Ullage installed a healthy mapping, but
the native Play action only reached `App Running`; the bridge exited with
`wine_exit=53` and no game surface appeared. The selected GameHub virtual prefix
was initialized, so the failure is now narrowed to the runtime/prefix launch
contract rather than depot selection or appinfo mapping. Release publication is
gated on resolving this reproduction with a matrix title.

### 7. GameHub component inventory and controlled retries

The user's GameHub attempts did provide useful runtime material. The current
engine inventory contains GameHub's Wine Proton 11.0 runtime, Apple GPTK 3.0-3,
two newly initialized virtual containers, SandboxFS manifests, and a downloaded
Windows Steam client component at:

```text
$HOME/Library/Application Support/com.gamemac.www/wine-engine/downloads/steam_client
```

That component contains the Windows `Steam.dll`, `Steam2.dll`,
`steamclient.dll`, `steamclient64.dll`, `tier0_s.dll`, `tier0_s64.dll`,
`vstdlib_s.dll`, and `vstdlib_s64.dll`, among its other client files. It does
not contain `lsteamclient`; a search of the GameHub engine after removing the
temporary test copy found no `lsteamclient` file. The downloaded client is
therefore useful for satisfying a game's `Steam.dll` lookup, but it is not the
missing Unix bridge.

GameHub's launch logs supplied the missing prefix contract: a virtual prefix is
combined with `WINEPREFIX_BASE`, `WINEARCH=win64`, the GameHub Wine/GPTK paths,
and `DYLD_INSERT_LIBRARIES` containing `libsandboxfs.dylib` plus the exact
per-container layer manifest. Replaying that contract made a `wine cmd /c ver`
probe return success and allowed a direct `notepad.exe` launch to create a
visible Wine window. This isolated the earlier `wow64.dll`/`wine_exit=53`
failure to the missing SandboxFS/base-prefix handoff rather than a general
renderer failure.

The first attempt to supply the missing bridge staged Ullage's experimental
x86_64 `lsteamclient.dll` into the GameHub base prefix. GameHub then loaded that
file and crashed in `steamclient_init`; its launch logs reported an access
violation and exit code 5. The file was moved recoverably to:

```text
$HOME/Developer/ullage-runtime-work/gamehub-staged-lsteamclient-x86_64.dll
```

and is no longer present in the GameHub base prefix. Its SHA256 matched
Ullage's current experimental artifact exactly, proving that this was our test
file and not a GameHub-supplied bridge.

After staging only GameHub's downloaded Steam client symlinks in the disposable
Peggle virtual prefix and adding that client directory to `WINEDLLPATH`, the
bridge progressed further: Wine's loader log confirmed that `Steam.dll` loaded.
The next call, `CreateInterface("SteamClient017")`, entered Ullage's
`lsteamclient` Unix side and returned an access violation from
`steamclient_init`. The native Steam client page showed Peggle as Running, but
no Peggle surface appeared and the bridge exited with code 5. The diagnostic
record is:

```text
$HOME/Developer/ullage-runtime-work/diagnostic-peggle-steamdll.log
$HOME/Developer/ullage-runtime-work/peggle-client-retry-20260826.png
```

This is now an ABI/runtime compatibility blocker: the lsteamclient module built
from Valve Proton's pinned Wine source is not yet proven compatible with
GameHub's modified `wine-11.0-gdbf9021e9406-dirty` runtime. The public GameSir
Wine checkout used for comparison also has no lsteamclient source of its own,
so it cannot by itself provide a drop-in replacement. No artifact is safe to
publish until the same Peggle matrix run produces an actual game surface.

A follow-up loader/layout retry made the blocker more specific. Without a Unix
sidecar beside the PE bridge, Wine reported that it could not load
`i386-windows/lsteamclient.so`. Adding temporary symlinks in both architecture
directories changed that to an explicit `dlopen` error: the native sidecar
imports `_lstrcpynA`, which GameHub's `x86_64-unix/ntdll.so` does not export.
The current Unix sidecar therefore is not load-compatible with this Wine
runtime yet. Those symlinks were test-only and are not a release layout; the
next build should eliminate or satisfy that symbol dependency before another
game launch.

The remaining test gate at that point was intentionally concrete: use the
exact GameHub SandboxFS/base-prefix launch contract, a client payload that
loads, and an lsteamclient build compatible with this Wine runtime; then verify
the Peggle window, Steam `App Running`/Stop lifecycle, and a clean bridge log.
TIS-100 (AppID `370360`) remained an additional matrix candidate, but its
native Play path had previously failed with Steam's `OS Error 0` because no
Ullage mapping was installed.

### 8. Successful matrix reproduction after the GameHub remediation

The source-backed Unix sidecar was rebuilt after adding the macOS-only
`<wchar.h>` include to the source patch itself. The final sidecar is an
x86_64 Mach-O dylib with SHA256
`6fce7da81364ba1ee16087a53215f99b3a2989173777f85248b6b1f3a8dd992f` and is
laid out with the loader-visible `i386-windows`, `x86_64-windows`, and
`x86_64-unix` directories. The two temporary Unix-side architecture aliases
are required by this GameHub loader layout and are included in the runtime
package rather than being treated as a source-tree change.

Using the native Steam helper's Play button, Peggle Deluxe (AppID `3480`)
then launched through the installed Ullage mapping with
`PRESERVE_STEAM_TRANSPORT=0`. Steam showed `Peggle Deluxe - Running`; the
window was titled `Peggle Deluxe 1.01`; and a CoreGraphics capture reached the
rendered `CLICK TO PLAY!` title screen. The final host capture is:

```text
/Users/danhimebauch/Developer/ullage-runtime-work/peggle-native-steam-final-title-20260826.png
```

This is the first successful real game surface from the known-good matrix on
this Mac. A separate run with `PRESERVE_STEAM_TRANSPORT=1` also created a
game window but captured black, so clean transport is the working default for
this host; preserving Steam's injected transport/overlay libraries remains a
separate compatibility mode.

The native Stop confirmation changed Steam's content log to `Terminating` and
the Library to `Stopping`, but GameHub's reparented `popcapgame1.exe` did not
exit automatically. Killing only the exact test tree returned the content log
to `Fully Installed` at `12:56:09`. This is a genuine lifecycle defect: Ullage
needs prefix-scoped process-tree tracking or a stronger reaper association,
and the UI should surface cleanup failure instead of leaving Steam in
`Stopping`.

### 9. Setup and onboarding improvements indicated by this run

The first-run path should expose a single preflight/doctor result before the
user presses Play. It should check Rosetta, native Steam, the exact bundled
`steam_dev.cfg` path, a Windows PE depot, Wine/GPTK, the GameHub base-prefix
and SandboxFS manifest, client-root files, all architecture-specific
lsteamclient sidecars, the x64 forwarder, and disk headroom. Each failed
check should name the missing path and the next action.

The setup wizard should offer an explicit “Windows depot” step, verify a PE
entry such as `Peggle.exe` or `tis100.exe` before creating a mapping, and
automatically discover GameHub's launch contract. Mapping records should
retain the prefix base, `WINEARCH`, SandboxFS manifest/library, client root,
bridge artifact version, and transport mode so a later launch does not depend
on hidden machine state.

The artifact path should prefer a signed or checksum-verified prebuilt
bridge/forwarder release pinned to the Wine/Proton source and patch series.
Only fall back to a scoped component build when no compatible artifact exists;
the UI should show the source commit, patch set, compiler architecture, and
why a full Proton build is not required.

Error reporting should translate the observed failures into actions: `OS Error
0` means no usable Ullage mapping; `kernel32.dll`/`wow64.dll` means the
GameHub base-prefix/SandboxFS handoff is incomplete; missing `Steam.dll` means
the Windows client root is absent; a missing sidecar or `dlopen` symbol names
the incompatible artifact; a black surface selects clean transport; and a
stuck `Stopping` state offers “clean this game's Wine tree” with the exact
prefix and processes shown.

Finally, the wizard should warn when free space falls below a build threshold,
offer the external volume for source/build/archive storage, and warn that the
observed FAT32 volume is suitable for disposable artifacts but has filename
and file-size constraints. Install/remove should be transactional and leave a
recoverable mapping receipt, so a failed first attempt does not require
manually undoing Steam depot or prefix state.

### 10. Native Steam Stop remediation and generic process association

The lifecycle defect was not specific to Peggle or PopCap. The first reaper
implementation selected game processes only when their command line still
contained the Wine `Z:` spelling of the install root. GameHub's launcher
exited after spawning the game, and the surviving guest executable was
reparented to PID 1 with no install-root argument. Its `lsof` record still
showed both the physical game install and the selected virtual prefix.

The reaper now accepts any guest `.exe` that is prefix-scoped and either keeps
the mapped install root in its command line or has an open handle under the
canonical physical game root. It parses executable paths containing spaces up
to the first `.exe` suffix, excludes known Wine infrastructure helpers, and
does not use global process-name kills. The bridge's native Steam stop path
also gives the exact Wine launcher a bounded TERM grace period; if that
launcher ignores TERM, it is force-reaped and the same prefix-scoped game
association cleanup runs. This applies to launchers that spawn a different
game executable, not just this title.

The focused shell/Python checks and full `make check` pass after this change;
the bridge regression suite now also covers a TERM-ignoring launcher and
requires the bounded fallback to complete.
The post-change native UI run launched Peggle Deluxe (AppID `3480`) at
`13:28:30`; Steam showed `Peggle Deluxe - Running` and CoreGraphics saw the
Wine window `Peggle Deluxe 1.01`. After Stop and Confirm at `13:29:14`, the
bridge recorded a native stop request, reaped the detached game PID
`50084`, and returned the selected prefix to a clean state. Steam's content
log returned to `Fully Installed` at `13:29:19`, and a fresh Steam Helper
screenshot showed Play with no Running suffix. No Peggle, PopCap, wineserver,
or Ullage bridge process remained afterward.

The bridge log reports `wine_exit=137 signal_received=1` for this run because
GameHub's `start.exe` wrapper ignored TERM and required the bounded fallback
SIGKILL. Steam's application state is clean; normalizing that user-requested
forced-stop status to the existing `143` convention is a follow-up polish,
not a process-leak blocker.

### 11. Second matrix reproduction and current host state

The runtime gap is now closed for this host by the disposable, source-backed
artifact package staged at:

```text
/Users/danhimebauch/Developer/ullage-runtime-work/ullage-bridge-artifacts-20260826
```

It contains the x86_64 Unix sidecar, the i386 and x86_64 Windows bridges, and
the canonical-name x64 Steam client forwarder. No full Proton distribution
build was needed; the scoped lsteamclient components were enough for this
known-good game validation. The later checksum-verified package and release
gate are recorded in section 15.

TIS-100 (AppID `370360`) was then mapped with `ullage-install` into GameHub's
container 2 using its recorded base prefix, `WINEARCH=win64`, and SandboxFS
manifest. The already downloaded Windows depot is 50,190,783 bytes and its
`tis100.exe` entry is PE32. Native Steam Play through the helper reached
`TIS-100 - Running` at `13:38:48`. CoreGraphics found a Wine window titled
`TIS-100`, and the captured surface showed the rendered BIOS/diagnostic screen:

```text
/Users/danhimebauch/Developer/ullage-runtime-work/tis100-native-steam-title-20260826.png
SHA256 1442841125c04cd6b794244016a5b5ac4665f3dc8f8d1b5d354ef4a9f19134c1
```

The native Stop confirmation was accepted at `13:40:20`; Steam returned to
`Fully Installed` at `13:40:25`, and the helper showed Play again. The bridge
logged `native Steam requested stop`, `reaped_helper_pids=none`,
`reaped_game_pids=none`, and `wine_exit=137 signal_received=1`. No TIS-100,
selected-prefix, bridge, or wineserver process remained. A few unrelated
`start.exe` processes from older GameHub experiments remained outside the
selected prefix and were intentionally not touched, which confirms the
reaper's scope boundary.

This gives two known-good matrix reproductions on the new Mac: Peggle Deluxe
(AppID `3480`, including a detached `popcapgame1.exe` cleanup) and TIS-100
(AppID `370360`, including the GameHub base/SandboxFS contract). Both rendered
through native Steam Play and returned to the installed Play state after native
Stop. The remaining host gap is optional MinGW probe coverage; it is not
required for the tested launch/renderer/Stop path.

### 12. Machine-interface onboarding

The first GUI-facing discovery pass found two practical integration hazards.
GameHub's virtual-container registry does not repeat the Wine installation ID
on every virtual container; the ID is inherited from the base container. Also,
older single-entry Ullage state records use `entry` at the top level while
newer multi-launch records use an `entries` array. Treating either shape as
the only shape made healthy Peggle and TIS-100 mappings appear to have no
Windows launch option. `ullagectl` now resolves both shapes and reads the
GameHub registry inheritance in core.

The separate GUI must therefore use `bin/ullagectl` for runtime and library
discovery. It should not infer GameHub paths, inspect `appinfo.vdf`, or parse
the text output of `ullage-install` and `ullage-remove`. The new read-only
`plan` response is the source for a Configure screen, and all handled errors
carry stable codes such as `steam_running`, `runtime_incomplete`,
`prefix_missing`, and `mapping_stale`.

### 13. Compact GUI onboarding

The first compact GUI pass exposed two practical issues. A large persistent
sidebar/detail layout hid the per-game runner choice and had no visible place
for the global Windows-depot setting. It was replaced with a small
launcher-style list: installed games are the default view, a filter exposes
cached not-installed entries, and selecting a game opens its runner picker and
prepare/repair controls. The Steam status pill opens the guarded depot-mode
control, while runtime checks remain behind the gear popover.

An initial implementation tried to identify not-installed games by walking
`Steam/userdata/*/config/localconfig.vdf`. The packaged app could block in
that directory under macOS privacy handling even though the same command ran
from a terminal. The GUI then appeared to refresh forever. The core now uses
the already-loaded `appcache/appinfo.vdf` records for a responsive cached
catalog, marks those records `not_installed`, and documents that the cache is
not proof of ownership. The search field is therefore part of the minimal
launcher surface rather than an optional diagnostic.

### 14. Ten-title new-machine validation and cleanup

The next-machine pass installed, mapped, launched, stopped, and removed ten
small entitled Windows depots through native Steam: Half-Life (70),
Expendabros (312990), Shantae (345820), Windjammers 2 (1114290), Fight Crab
(1213750), EXAPUNKS (716490), Overcooked (448510), DREDGE (1562430), Crashday
Redline Edition (508980), and SpeedRunners (207140). All ten reached the
Ullage bridge; native Stop returned Steam to Play for the titles where a game
surface or process remained; every mapping was removed after uninstall.

The run exposed several setup issues that are now part of the generic
acceptance contract:

* Steam's external-library `apps` index was empty immediately after a fresh
  install, so Fight Crab initially appeared not installed. The authoritative
  `appmanifest_*.acf` files are now scanned under every configured library
  root as a fallback.
* GameHub's x64 prefix initially exposed `steamclient64.dll` as a stock
  symlink. The canonical-name forwarder must be a regular file matching the
  bridge artifact; the original symlink was preserved and restored after the
  x64 trials.
* `--cloud-native` correctly refused titles with no supported Windows Cloud
  root. Those installs were retried without Cloud mapping rather than forcing
  an invented path. Half-Life's native Cloud sync and prompt were observed;
  no changed-save round trip is claimed by this run.
* Overcooked first reproduced Steam's native `OS Error 0` before mapping, then
  launched through Ullage after the mapping was installed. DREDGE and
  SpeedRunners reached Running but did not expose a visible game surface in
  the available capture; process, stop, and prefix-cleanliness evidence was
  still recorded separately from renderer support.
* The X-Wing install flow presented a Disney EULA. It was canceled rather than
  accepting a legal agreement without an action-time confirmation, and
  Crashday was used as the replacement tenth title.
* Half-Life exposed a Steam cleanup race: quitting while native uninstall was
  still in `Files Missing`/`Uninstalling` caused Steam to queue verification and
  redownload on the next launch. Recovery is to stop Steam, preserve the exact
  AppID manifest and residue in an external archive, remove only that AppID's
  metadata, and verify the library before restarting. Other library entries
  must not be swept as part of this recovery.

The internal disk started near exhaustion at roughly 1--2 GB free. Disposable
Steam caches, ignored build outputs, old Downloads artifacts, Docker's unused
builder cache, and re-downloadable language/app caches were removed or moved
to `/Volumes/NO NAME` archives. This recovered roughly 10 GB of headroom; the
final audit after package staging measured about 9 GB free. Project source,
active toolchains, Android/Notion data, Codex state, and Docker images were
retained; the desired 20 GB target was not pursued by deleting data with
unclear ownership.

### 15. Reproducible bridge package

The manually assembled bridge is now a small package produced by
`ullage-patches/scripts/package-bridge-runtime.sh`. The package contains
only the x86_64 Unix sidecar, i386 and x86_64 Windows sidecars, and the x64
canonical-name forwarder. Its manifest records the package version, artifact
sizes and SHA-256 digests, the patch repository commit, and the patch-manifest
digest. It does not require or distribute a full Proton runtime.

`ullagectl runtime install` verifies the manifest before copying, stages a
versioned directory under `~/.ullage/runtimes`, verifies the copy, and then
updates the active pointer atomically. Mapping configs and session receipts
carry the package ID, version, manifest path, and digest. The packager
normalizes archive ordering, ownership, modes, and timestamps; two independent
runs of `2026.08.26-3` produced the same SHA-256:
`9413215f4a72d19adf2fe2024d16b4e7755542b34db94ea694005ea580212a4b`.

The package was installed and verified on this Mac, then tested against the
known-good TIS-100 matrix row (AppID `370360`). The game process loaded the
packaged x86 lsteamclient and Steam API, native Steam showed Running and the
Stop confirmation returned it to Play, and the receipt recorded a clean Wine
prefix. The package was published as tag `runtime-macos-2026-08-26-3` in
`ullage-patches`.

### 16. Public release bootstrap and fresh-state rehearsal

The package retrieval path was simplified after `ullage-patches` became public.
The first direct-URL check returned HTTP 404 while the repository was still
private, and the initial bootstrap design considered GitHub API or `gh`
authentication. Once the repository visibility changed to public, the pinned
release URL worked with a plain HTTPS request, so no GitHub token, `gh` login,
or API fallback is needed for a new machine.

The checked-in `runtime/releases.json` lock now identifies the release tag,
asset, runtime ID, version, archive size (`9,493,440` bytes), SHA-256
(`9413215f4a72d19adf2fe2024d16b4e7755542b34db94ea694005ea580212a4b`), and
public URL. `runtime fetch` caches the archive, verifies it before opening it,
rejects traversal, links, devices, duplicate paths, and oversized expansion,
then verifies the package manifest and every artifact before activation.

On this Mac, a fresh state root at `/tmp/ullage-isolated.O0qwed` fetched that
public archive, installed `macos-x86_64-lsteamclient` version `2026.08.26-3`,
passed `runtime verify`, and made `doctor` report no blocking checks. A
separate disposable initialized prefix staged the canonical
`steamclient64.dll` as a regular file and restored its original stock symlink.
The package and forwarder tests also exercise atomic activation, retained
rollback pointers, archive tamper rejection, and manifest/artifact mismatch
reporting without touching the user's normal Steam state.

The new `smoke` command is intentionally a read-only bridge preflight. It
checks the installed/mapped 32-bit and x64-forwarder controls and emits the
native Steam `steam://rungameid/` actions, but Play, Stop, Cloud writes, and
other game state changes remain explicit acceptance steps. The fresh
EXAPUNKS install completed and mapped correctly, but its native launch exited
early with Wine status 5 before a Stop event, so it is not a suitable x64
control for this rehearsal. Katamari Damacy REROLL was then selected from the
documented known-good x64 matrix. Steam presented its publisher EULA before
the depot download could begin; that legal prompt is an explicit user-action
boundary and was not accepted by Ullage. On a later refresh Steam had moved
past the prompt and downloaded the 3.3 GB depot, so the prompt was handled
outside this run. The fresh public-package mapping launched Katamari through
native Steam and kept the Windows process alive for about 35 seconds while
loading the packaged x64 bridge and overlay injection, but Wine then exited
with status 5 before a usable game surface or native Stop event. It is not
counted as a current x64 renderer/Stop pass; the earlier matrix evidence is
preserved separately.

For a current package lifecycle control, the documented Stellar Mess row
(AppID `1507530`, 20.81 MB, win32) was downloaded to the external library and
mapped with version `2026.08.26-3`. Native Steam showed Running, the bridge
logged the packaged runtime and Steam overlay injection, and the native Stop
confirmation returned the page to Play. Its receipt records
`native_stop_observed=true`, `wine_exit=137`, and a clean prefix. This validates
the public package and supervisor on this Mac, but it is a 32-bit control and
does not independently validate the x64 forwarder.

The optional Steamworks probe also hit a useful diagnostic boundary during
this rehearsal. TIS-100's older API DLL uses the legacy `SteamClient` export,
so the probe now supports both that entry point and the newer
`SteamInternal_CreateInterface` export. Copies of the TIS-100 and EXAPUNKS
API DLLs loaded under an ordinary shell-launched bridge but exited with Wine
status 5 during `SteamAPI_Init`; because that is not Steam's Play-launched
environment, it is not counted as a shipped-game feature failure. A temporary
x64 probe copied from Katamari's `steam_api64.dll` was also launched through
native Steam; it logged `steam_api_load=1` and
`steam_api_init_begin=1`, then ended with status 5 without a completed API
result. The probe therefore remains diagnostic rather than a current feature
pass. The native TIS-100 and Stellar Mess runs still loaded the packaged bridge
and native Steam client and completed native Stop cleanup.

### 17. macOS Steam process detection

While Katamari was downloading, `ps` showed the native `steam_osx` process and
its CEF helpers, but `ullagectl status` briefly reported Steam stopped. The
cause was macOS truncating the `comm` column to the account prefix; Ullage's
whitespace split then treated `Application Support/Steam/.../steam_osx` as a
different path. The process snapshot now uses the untruncated `ucomm` column
and keeps a suffix check for full command paths, including `Steam Helper`.
The first regression fixture made the suffix check too broad and classified a
test command's `--steam-root /tmp/Steam` argument as the client; the matcher is
now limited to real Steam executable suffixes and the fixture covers that
negative case. It also deliberately excludes the long-lived `ipcserver`, which
is supervised separately by Steam and must not keep normal appcache operations
blocked after the client exits.

### 18. Cross-machine x64 status-5 and loader-order regression

The status-5 Katamari crash reported from a second Mac was reproduced on this
host with the same public package, using both Katamari and the documented
x64 Gravity Circuit control. The Unity crash report identifies
`lsteamclient.dll` and the read address `0xBEEF`; GameHub's Wine log shows the
same value is Wine's guarded failure path when the native Steam client call
does not initialize. The four public bridge artifacts were byte-identical to
the earlier manually assembled set, so downloading or rebuilding the package
was not the missing step.

The failing launch had two relevant bridge changes: an intermediate shell
exported `WINEPREFIX_BASE`, `WINEARCH`, and `DYLD_INSERT_LIBRARIES`, and the
package's `x86_64-windows` directory was placed ahead of the package root in
`WINEDLLPATH`. Removing only the shell was insufficient. Restoring the
package-root-first search order and passing the computed environment directly
to Wine fixed the generic boundary without a title-specific override.

With Ullage commit `72d0c70` and the unchanged public runtime package
`2026.08.26-3`, Gravity Circuit rendered its language-selection screen from
the external Steam library. Native Steam Stop produced the AppID-scoped
termination event, returned the page to Play, and the receipt recorded
`native_stop_observed=true`, `wine_exit=137`, and a clean prefix. The fix is
covered by the bridge environment regression and the full `make check` suite;
the runtime package was deliberately not republished because no artifact
changed.

The post-fix x64 retest kept the boundary distinction explicit. Megabonk
rendered its default DX11 menu and completed native Stop cleanup. Katamari
remained alive long enough to load its Unity crash handler and completed the
same native Stop cleanup, but the available capture was black, so it remains
an x64 renderer near-miss rather than a pass. The unchanged package also
continued to pass the Stellar Mess win32 transport/Stop control. These runs
did not change the runtime artifacts or justify a new `ullage-patches` release.

The unchanged package was also repeated with the small TIS-100 win32 control.
Native Steam showed `TIS-100 - Running`, and the native Stop confirmation
returned the page to Play. The receipt at
`~/.ullage/sessions/370360/last.json` recorded
`native_stop_observed=true`, `wine_exit=137`, `signal_received=true`, and a
clean prefix. The page showed `Steam Cloud Out of Date` before launch, so this
run does not add a new Cloud round-trip claim. The full-display capture was
occluded by the Codex window; the prior TIS-100 rendered-surface evidence
remains the renderer pass, while this repetition is transport/Stop evidence
only.

### 19. Native Steam client exit fallback

The native Stop path and native Steam-client shutdown are separate lifecycle
events. During a current Gravity Circuit x64 run using the unchanged public
package `2026.08.26-3`, quitting Steam while the game was active displayed
Steam's `Waiting for Gravity Circuit to shut down...` dialog. Steam then exited
without emitting the AppID-scoped Stop event. Ullage commit `f3f2bf1` watched the
exact incumbent `steam_osx` process for this launch, routed the client exit
through the existing bridge signal path, and ran the prefix-scoped reaper.

The resulting receipt at `~/.ullage/sessions/858710/last.json` recorded
`native_stop_observed=false`, `steam_client_exit_observed=true`,
`signal_received=true`, `wine_exit=137`, and `prefix_clean=true`. Process
inspection confirmed that the bridge, Gravity Circuit, Wine helpers, and
Steam were gone afterward. This is a generic shutdown fallback, not a
title-specific kill or a replacement for the ordinary native Steam Stop
flow; `ipcserver` is intentionally not used as the client-aliveness signal.

### 20. Current Steamworks and Cloud probe boundaries

The current x64 diagnostic probe passed through the public package on
2026-08-27 using an unmodified copy of Gravity Circuit's `steam_api64.dll`.
It initialized Steam, matched AppID `858710`, returned the logged-on identity
and ownership flags, enumerated 53 achievements and zero DLC, requested stats,
and shut down cleanly. This is useful API-level evidence, but it is a staged
probe rather than a trace from the shipped game process. Its
`IsOverlayEnabled=0` result must not override the separate native-run evidence
that `gameoverlayui` attached to visible game processes.

Two onboarding boundaries remain easy to misread. `SteamAPI_IsSteamRunning=1`
can outlive the actual `steam_osx` client when only stale IPC state remains, so
probe setup should verify the native client process separately. Also, the
Steam Helper screenshot can become black or occluded when a fullscreen Wine
game owns the frontmost surface; use fresh screenshots after each action and
the bridge/Steam logs for lifecycle evidence. The current EXAPUNKS run showed
the native Cloud synchronization start and a healthy `gameinstall` mapping,
then stayed on its loading surface; quitting Steam used the client-exit
fallback cleanly, but no Cloud upload was inferred. Eets then provided a
different boundary: its `gameinstall` mapping and rendered main menu passed,
but Steam explicitly reported `Sync Disabled`/`AutoCloud is disabled` and no
`gameoverlayui` process attached. Native Stop, Steam uninstall, and Ullage
mapping cleanup still passed, so this title is useful for separating title
capability from bridge lifecycle correctness. Portal 2 exposed a separate
Steam onboarding mismatch: the install dialog reported 11.88 GB even though
the appinfo estimate was much smaller. Its external-volume reservation stayed
at 1% while preallocating 2.155 GB at roughly 1 MB/s, so the queued download
was paused and uninstalled as a bounded check rather than treated as a small
test. Steam removed the manifest and staging area with `No Error`, and no
Portal 2 row was added to the acceptance matrix.
The current-package Peggle repeat found a separate title boundary: the
existing win32 depot launched with x86 lsteamclient and `gameoverlayui`, but
its fullscreen surface stayed on the loading screen for about one minute at
high child CPU. The generic Steam-client exit fallback eventually reaped the
game and helpers cleanly; Ullage then restored the original launch entry and
left the user's depot installed.
