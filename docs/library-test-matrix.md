# Steam library test matrix

This ledger records the 2026-08-25 library-coverage run for the native macOS
Steam launch boundary. Each counted title was started from the ordinary Steam
Play button in the native `Steam Helper.app` target. A renderer pass requires a
fresh desktop capture containing the game surface; a Steam page showing
“Running” is not enough. Stop passes require the native Stop flow, the AppID
`Terminating` event, a bridge exit, and no selected-prefix Wine helpers left.

## Coverage target

* Entitled AppIDs inventoried: **521**.
* Minimum for the requested 10%: **53 unique AppIDs**.
* Unique AppIDs tested in this run: **41**.
* Remaining: **12**.
* Storage is being kept bounded by installing small titles, testing them, and
  uninstalling them through Steam before moving on.

Runtime for this pass is the GameHub Wine installation `10000073`, GPTK
`gptk-3.0-3`, the external lsteamclient runtime, and the shared experimental
prefix with the canonical x64 `steamclient64.dll` forwarder. These paths are
host-local evidence only; they are not project dependencies.

## Current run

Status letters: `P` proven, `I` indirect/provisional, `F` failed, `—` not yet
run. “Renderer” is intentionally separate from launch and Steamworks evidence.

| AppID | Title | Arch | Launch | Renderer | Native Stop | Cleanup | Notes |
| ---: | --- | :---: | :---: | :---: | :---: | :---: | --- |
| 848350 | Katamari Damacy REROLL | win64 | P | P | P | P | Visible menu; native Stop confirmed; prior relaunch also returned to Play. |
| 1086010 | 198X | win64 | P | P | P | P | Visible rendered scene; Stop returned to installed state. |
| 1740930 | JellyCar Worlds | win64 | P | P | P | P | Visible book/cutscene content after the earlier Unity black-screen classification. |
| 990630 | The Last Campfire | win64 | P | P | P | P | User-visible rendered run; Stop clean. |
| 304430 | INSIDE | win64 | P | P | P | P | Fresh 30s and 50s captures showed the rendered Playdead's INSIDE title surface; native Stop remained clean. |
| 334940 | Yoku's Island Express | win64 | P | F | P | P | Wine-owned `Steam Error: Application load error 3:0000065432`; no game surface proven. |
| 356400 | Thumper | win64 | P | F | P | P | Default `THUMPER_win8.exe` reached Steam Running but showed Wine-owned `Application load error 3:0000065432`; native Stop returned cleanly. The chooser's DX9 entry exposed the pre-fix multi-option gap and produced Steam `OS Error`; the installer now redirects all Windows `.exe` options for a fresh retest. |
| 584400 | Sonic Mania | win32 | P | P | P | P | Visible game surface; native Stop confirmed; no Sonic/Wine helpers remained. |
| 609320 | FAR: Lone Sails | win64 | P | P | P | P | Initial unbridged launch returned Steam `OS Error 0`; adding the missing Ullage mapping for launch entry 0 fixed it. Loading scene and menu rendered; bridge logged `wine_exit=143`. |
| 3480 | Peggle Deluxe | win32 | P | P | P | P | Visible loading/title screen; Steam warned about 32-bit macOS but Ullage launched and stopped cleanly. |
| 8400 | Geometry Wars: Retro Evolved | win32 | P | P | P | P | Visible title/menu with effects; native Stop clean. |
| 3483 | Peggle Extreme | win32 | P | P | P | P | Newly downloaded 22 MB depot; mapped, rendered title screen, stopped cleanly, and was uninstalled through Steam. |
| 1812290 | The Elder Scrolls: Arena | win32 | P | P | P | P | Newly downloaded 105 MB DOSBox depot; full-screen title rendered; preserved DOSBox working directory and stopped cleanly. |
| 1368430 | Streets Of Kamurocho | win32 | P | F | P | P | Newly downloaded 34 MB depot; Wine reported `DirectX 11 Issue: Issue finding adapter for DirectX 11`; native Stop still reaped the session cleanly. |
| 1018130 | Castle Break | win64 | P | F | P | P | Newly downloaded 53 MB depot; Wine reported `HRESULT 0x80070057` from `CheckMultisampleQualityLevels` before a game surface appeared; native Stop was clean. |
| 567090 | 8-Bit Bayonetta | win32 | P | I | P | P | Newly downloaded 55 MB Unity depot; Steam Play opened and rendered Unity's `8 Bit Bayonetta Configuration` window, but the title's separate Play handoff was not exercised; native Stop was clean. |
| 3463050 | Dreams of Aether | win64 | P | F | P | P | Newly downloaded 60 MB depot; Wine reported `HRESULT 0x80070057` from `CheckMultisampleQualityLevels` before a game surface appeared; native Stop was clean. |
| 3590 | Plants vs. Zombies: Game of the Year | win32 | P | P | P | P | Newly exercised 49 MB depot; PopCap loading and live level UI rendered; appinfo has a Cloud quota but no supported Windows root, so native Cloud mapping is intentionally absent. |
| 449040 | Jesus Christ RPG Trilogy | win32 | P | I | P | P | Trilogy selector rendered. First run exposed an orphaned `jcrpg/Game.exe`; the scoped supervisor/reaper fix was rerun and native Stop then left no game or Wine helpers. Direct child-game handoff remains a follow-up. |
| 3784030 | RACCOON: Coin Pusher Roguelike | win64 | P | P | P | P | Fresh run rendered the title screen and menu; native Stop returned to Play and left no RACCOIN/Wine helpers. |
| 3520070 | Megabonk Demo | win64 | P | P | P | P | Freshly downloaded 51 MB / 157 MB installed demo; both DX11/default and DX12 chooser options rendered the menu through distinct per-entry launchers. The DX12 selection preserved one Steam argument; native Stop returned cleanly for both runs. |
| 2921380 | Caribbean Crashers | win32 | P | F | P | P | Fresh run reached Steam Running but produced only NW.js crashpad/GPU/utility zombies and no visible game surface. After the supervisor fix, native Stop logged the Steam termination event, returned to Play, and left no Caribbean/Wine helpers. |
| 2827560 | 100 Romantic Cats | win64 | P | P | P | P | Freshly downloaded 49 MB depot; full-screen Unity coloring scene rendered with Steam overlay visible; native Stop returned cleanly. |
| 2932930 | 100 Korea Cats | win64 | P | P | P | P | Freshly downloaded 72 MB depot; full-screen Unity title/menu rendered with Steam overlay visible; native Stop returned cleanly. |
| 370360 | TIS-100 | win32 | P | P | P | P | Freshly downloaded 48 MB depot; TIS-100 BIOS/title window rendered with Steam overlay visible. Native page showed `Steam Cloud Out of Date` before launch; Stop returned cleanly. |
| 1812390 | The Elder Scrolls II: Daggerfall | win32 | P | P | P | P | Freshly downloaded 1.0 GB DOSBox depot; the two-option chooser selected Full Screen, then the title menu rendered after a slow boot. Native Stop returned cleanly. |
| 3347820 | CloverPit Demo | win64 | P | P | P | P | Freshly downloaded 330 MB Unity depot. A first mapping used the wrong install-root base and produced a missing launcher; remapping against the game root fixed it. The photosensitivity warning rendered and native Stop returned cleanly. |
| 1506510 | The Ramp | win64 | P | P | P | P | Freshly downloaded 686 MB Unity depot; a solid orange Unity surface appeared behind native Steam, then native Stop returned cleanly with no Wine/game helpers left. This run did not capture the title menu. |
| 405640 | Pony Island | win32 | P | F | P | P | Freshly downloaded 367 MB Unity depot. Default launch failed at `InitializeEngineGraphics`; `-force-d3d9` and `-force-glcore` produced the same failure. Native Stop cleanly reaped each attempt. |
| 375820 | Human Resource Machine | win32 | P | F | I | P | Freshly downloaded 165 MB 32-bit depot. `--cloud-native` mapped `WinAppDataRoaming` to `~/Library/Application Support/Ullage/375820`; Steam changed from `Cloud Out of Date` to the checked Cloud state after synchronization. The game exited with Wine status 3 before a surface appeared, so native Stop was not needed. |
| 48000 | LIMBO | win32 | P | F | P | P | Freshly downloaded 99 MB 32-bit depot. The run produced a game-originated `Pixel shader error` dialog rather than a playable surface; native Stop returned cleanly and left no Wine helpers. |
| 204360 | Castle Crashers | win32 | P | P | P | P | Freshly downloaded 119 MB depot. The game reached a controller prompt and a live red game surface behind Steam; native Stop confirmed clean shutdown with no Wine/game helpers. Appinfo exposed no supported Windows Cloud root, so no native Cloud mapping was applied. |
| 1986840 | POPGOES Arcade | win32 | P | F | I | P | Freshly downloaded 204 MB Clickteam/Fusion depot. Steam reached App Running, but the game exited with Wine status 3 before a surface. Diagnostic logging showed the 32-bit D3D11 path falling back to Wine Vulkan and crashing in MoltenVK (`VK_ERROR_FEATURE_NOT_PRESENT`); no native Stop was needed after the early exit. |
| 1794680 | Vampire Survivors | win64 | P | P | P | P | Freshly downloaded 1.1 GB Unity depot. Native page showed the checked Cloud state; `--cloud-native` mapped `gameinstall` and `WinAppDataRoaming`, and Wine created `steam_autocloud.vdf` markers in the mapped prefix. The photosensitivity warning rendered, two Play cycles reached Stop, and both native Stops reaped the Wine session cleanly; no actual save was created. |
| 1586800 | Lil Gator Game | win64 | P | P | P | P | Freshly downloaded 484 MB Unity/D3D12-shaped depot. The title menu rendered with D3DMetal logging (`D3D11 timestamp query` only); native Stop returned to Play with no residual Wine/game helpers. Appinfo exposed no supported Windows Cloud root. |
| 1388770 | Cruelty Squad | win64 | P | P | P | P | Freshly downloaded 548 MB Godot depot with `steam_api64.dll`. A live 3D game window rendered behind native Steam; native Stop returned to Play with no residual Wine/game helpers. `--cloud-native` mapped `WinAppDataRoaming`; only a renderer warning was logged. |
| 2702300 | Thrasher | win64 | P | P | P | P | Freshly downloaded 938 MB Unity/D3D12-shaped depot. The first install rolled back because the title has no supported Windows Cloud root; reinstalling without `--cloud-native` launched the normal Steam option and rendered the title screen. Native Stop returned to Play, reaped the Wine helper set, and left no selected-prefix processes. |
| 2019300 | Dokimon | win64 | P | F | P | P | Freshly downloaded 80 MB GameMaker depot with `steam_api64.dll` and `Steamworks_x64.dll`. `--cloud-native` mapped `WinAppDataLocal` and Steam showed the checked Cloud state, but Wine/GPTK failed `CheckMultisampleQualityLevels` with `HRESULT 0x80070057` before a surface. Native Stop still returned to Play with no residual Wine/game processes. |
| 606150 | Moonlighter | win64 | P | F | P | P | Freshly downloaded 1.2 GB Unity depot. The baseline, `-force-d3d9`, and `-force-glcore` launches all stayed on a black game surface after extended waits; each native Stop returned to Play and reaped the session. The title has no supported Windows Cloud root, so the temporary renderer options were cleared before uninstall. |
| 413410 | Danganronpa: Trigger Happy Havoc | win32 | P | P | P | P | Freshly downloaded 3.0 GB 32-bit depot. Steam warned that macOS cannot run 32-bit games, but the Launcher.exe path opened a visible title/Video Options surface through the i386 lsteamclient path. `--cloud-native` mapped the app's `gameinstall` root and the native Cloud icon was checked; Stop and Steam uninstall completed cleanly. |
| 403430 | ARCADE GAME SERIES: GALAGA | win64 | P | P | P | P | Freshly downloaded 763 MB Unity depot after accepting its EULA. The native Play path rendered the GALAGA title/notice surface; native Stop returned to Play and reaped the session, and Steam uninstall plus idempotent Ullage removal completed cleanly. `--cloud-native` mapped `WinAppDataRoaming`. |

## Per-title evidence

The bridge log and Steam content log are the authoritative lifecycle artifacts.
Temporary screenshots are host-local and may be removed after the result is
transcribed here.

| AppID | Bridge log | Steam content evidence |
| ---: | --- | --- |
| 609320 | `~/.ullage/logs/609320-far.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `14:00:37` Terminating; `14:00:40` Fully Installed |
| 3483 | `~/.ullage/logs/3483-peggle-extreme.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `14:14:42` Terminating; `14:14:45` Fully Installed |
| 3480 | `~/.ullage/logs/3480-peggle.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `14:04:06` Terminating; `14:04:08` Fully Installed |
| 8400 | `~/.ullage/logs/8400-geometry-ullage.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `14:06:53` Terminating; `14:06:55` Fully Installed |
| 1812290 | `~/.ullage/logs/1812290-arena.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `14:56:39` Terminating; `14:56:41` Fully Installed |
| 1368430 | `~/.ullage/logs/1368430-streets.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `15:00:37` Terminating; no Wine helpers remained after the stop |
| 1018130 | `~/.ullage/logs/1018130-castle.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `15:03:16` Terminating; no Wine helpers remained after the stop |
| 567090 | `~/.ullage/logs/567090-bayonetta.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `15:08:15` Terminating; no Wine helpers remained after the stop |
| 3463050 | `~/.ullage/logs/3463050-dreams.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `15:11:46` Terminating; no Wine helpers remained after the stop |
| 3590 | `~/.ullage/logs/3590-pvz.log`; `native Steam requested stop`; `reaped_helper_pids=...`; `wine_exit=143 signal_received=1` | `15:15:56` Terminating; no Wine helpers remained after the stop |
| 449040 | First run at `15:21:58` left an orphan `jcrpg/Game.exe`; rerun at `15:34:44` logged `native Steam requested stop`, `reaped_helper_pids=...`, and `wine_exit=143 signal_received=1` with no leftovers | First run required manual cleanup; rerun returned to installed state cleanly |
| 3784030 | `~/.ullage/logs/3784030-raccoin.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `15:58:32` App Running; `16:00:18` Terminating; `16:00:21` Fully Installed |
| 3520070 | `~/.ullage/logs/3520070-multilaunch.log`; default run logged `args=0`, DX12 run logged `args=1`; both logged `native Steam requested stop`, `reaped_helper_pids=...`, and `wine_exit=143 signal_received=1` | `20:35:02` default App Running; `20:36:24` Terminating; `20:36:27` Fully Installed; `20:40:31` DX12 App Running; `20:41:38` Terminating; `20:41:40` Fully Installed |
| 2921380 | `~/.ullage/logs/2921380-caribbean.log`; second run logged `native Steam requested stop`, `reaped_helper_pids=...`, and `wine_exit=5 signal_received=1` | `16:32:15` App Running; `16:33:32` Terminating; `16:33:36` Fully Installed |
| 2827560 | `~/.ullage/logs/2827560-cats.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `16:35:53` App Running; `16:36:50` Terminating; `16:36:52` Fully Installed |
| 2932930 | `~/.ullage/logs/2932930-korea.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `16:38:04` App Running; `16:39:12` Terminating; `16:39:15` Fully Installed |
| 370360 | `~/.ullage/logs/370360-tis100.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `16:45:58` App Running; `16:47:40` Terminating; `16:47:42` Fully Installed |
| 1812390 | `~/.ullage/logs/1812390-daggerfall.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `16:58:54` App Running; `17:01:09` Terminating; `17:01:11` Fully Installed |
| 3347820 | `~/.ullage/logs/3347820-cloverpit.log`; `native Steam requested stop`; `wine_exit=143 signal_received=1` | `17:05:52` App Running; `17:08:18` Terminating; `17:08:20` Fully Installed |
| 1506510 | `~/.ullage/logs/1506510.log`; `native Steam requested stop`; `reaped_helper_pids=none`; `reaped_game_pids=none`; `wine_exit=143 signal_received=1` | App Running after launch; native Stop at `17:27`; no residual Wine/game processes; game uninstalled afterward |
| 405640 | `~/.ullage/logs/405640.log`; three runs (default, `-force-d3d9`, `-force-glcore`) each logged `native Steam requested stop`, `reaped_helper_pids=none`, `reaped_game_pids=none`, `wine_exit=143 signal_received=1` | Each run reached App Running; desktop capture showed Unity `Failed to initialize player` / `InitializeEngineGraphics failed`; game uninstalled afterward |
| 375820 | `~/.ullage/logs/375820.log`; two runs exited with `wine_exit=3 signal_received=0`; no residual Wine/game processes | Native page showed `Steam Cloud Out of Date` before launch and a checked Cloud icon after synchronization; `~/.ullage/config/games/375820.cloud.json` records the native `WinAppDataRoaming` link; no save files were created |
| 48000 | `~/.ullage/logs/48000.log`; `native Steam requested stop`; `reaped_helper_pids=none`; `reaped_game_pids=none`; `wine_exit=143 signal_received=1` | Desktop capture showed the LIMBO run's pixel-shader error dialog; native page returned to Play; game uninstalled afterward |
| 204360 | `~/.ullage/logs/204360.log`; `native Steam requested stop`; `reaped_helper_pids=none`; `reaped_game_pids=none`; `wine_exit=143 signal_received=1` | Steam page reached App Running, desktop capture showed the red game surface and controller prompt; native Stop at `18:18` returned to Play with no residual Wine/game processes; game uninstalled afterward |
| 1986840 | `~/.ullage/logs/1986840.log`; early run and diagnostic rerun ended `wine_exit=3 signal_received=0`; no residual Wine/game processes | App Running at `18:27`; desktop capture showed no game surface; diagnostic rerun recorded Wine Vulkan fallback, `VK_ERROR_FEATURE_NOT_PRESENT`, and a MoltenVK access fault; depot uninstalled afterward |
| 1794680 | `~/.ullage/logs/1794680.log`; two runs each logged `native Steam requested stop`, `reaped_helper_pids=...`, `wine_exit=143 signal_received=1` | App Running at `18:34` and relaunch at `18:36`; desktop capture showed the rendered photosensitivity warning; native Cloud icon was checked and `~/.ullage/config/games/1794680.cloud.json` recorded both Windows roots; native Stop returned to Play with no residual helpers |
| 1586800 | `~/.ullage/logs/1586800.log`; `native Steam requested stop`; `reaped_helper_pids=none`; `reaped_game_pids=none`; `wine_exit=143 signal_received=1` | App Running at `18:45`; desktop capture showed the full Lil Gator title menu; native Stop returned to Play with no residual Wine/game processes; depot uninstalled afterward |
| 1388770 | `~/.ullage/logs/1388770.log`; `native Steam requested stop`; `reaped_helper_pids=none`; `reaped_game_pids=none`; `wine_exit=143 signal_received=1` | App Running at `18:52`; desktop capture showed a live Godot 3D game window; native Stop returned to Play with no residual Wine/game processes; depot uninstalled afterward |
| 2702300 | `~/.ullage/logs/2702300.log`; `native Steam requested stop`; `reaped_helper_pids=29923 29925 29931 29945 29951 29973 30016 30022`; `wine_exit=143 signal_received=1` | `19:04:50` App Running; `19:05:51` Terminating; `19:05:54` Fully Installed; desktop capture showed the rendered Thrasher title surface; depot uninstalled afterward |
| 2019300 | `~/.ullage/logs/2019300.log`; `native Steam requested stop`; `reaped_helper_pids=none`; `reaped_game_pids=none`; `wine_exit=143 signal_received=1` | `19:24:13` App Running; `19:25:37` Terminating; `19:25:39` Fully Installed; desktop capture showed the game-originated D3D error dialog; native Cloud icon was checked and `2019300.cloud.json` recorded `WinAppDataLocal`; depot uninstalled afterward |
| 606150 | `~/.ullage/logs/606150.log`; three runs (baseline, `-force-d3d9`, `-force-glcore`) each logged `native Steam requested stop`, helper reaping, and `wine_exit=143 signal_received=1` | `19:32:53`, `19:37:54`, `19:40:22` App Running; `19:35:33`, `19:39:14`, `19:41:38` Terminating; `19:43:47` Uninstalled; all desktop captures remained black; temporary launch options were cleared before uninstall |
| 413410 | `~/.ullage/logs/413410.log`; `native Steam requested stop`; `reaped_helper_pids=none`; `reaped_game_pids=none`; `wine_exit=143 signal_received=1` | `19:51:34` App Running; `19:53:08` Terminating; `19:56:12` Uninstalling and `19:56:12` Uninstalled; desktop capture showed the rendered Danganronpa launcher/title surface; native Cloud icon was checked; the remaining 240 KB directory contains Steam's `savedata.vfs` and `steam_autocloud.vdf` markers |
| 403430 | `~/.ullage/logs/403430-galaga.log`; `native Steam requested stop`; `reaped_helper_pids=none`; `reaped_game_pids=none`; `wine_exit=143 signal_received=1` | `20:02:41` App Running; `20:03:30` Terminating; `20:04:40` Uninstalling and `20:04:40` Uninstalled; desktop capture showed the rendered GALAGA title/notice surface; no residual game directory or selected-prefix helpers remained |

The ledger is updated as each additional entitlement is installed, exercised,
and cleaned up. It does not claim that a renderer pass proves every
Steamworks feature; those results remain in
[`steamworks-acceptance.md`](steamworks-acceptance.md).
