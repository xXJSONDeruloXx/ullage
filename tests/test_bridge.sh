#!/bin/sh
# Exercise the bridge with a fake Wine runtime, including supervisor races.
set -eu

ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/ullage-bridge-test.XXXXXX")
trap 'rm -rf "$TEMP_ROOT"' EXIT HUP INT TERM

write_script() {
    path=$1
    shift
    printf '%s\n' "$@" >"$path"
    chmod 755 "$path"
}

write_script "$TEMP_ROOT/fd-exec" \
    '#!/bin/sh' \
    'if [ "${1:-}" = "--preserve-fds" ]; then shift; fi' \
    'exec "$@"'
write_script "$TEMP_ROOT/reaper" \
    '#!/bin/sh' \
    'prefix=' \
    'kill_game=0' \
    'while [ "$#" -gt 0 ]; do' \
    '  case "$1" in' \
    '    --prefix) prefix=$2; shift 2 ;;' \
    '    --kill-game-processes) kill_game=1; shift ;;' \
    '    *) shift ;;' \
    '  esac' \
    'done' \
    'if [ "$kill_game" -eq 1 ] && [ -f "$prefix/orphan.pid" ]; then' \
    '  kill -KILL "$(cat "$prefix/orphan.pid")" 2>/dev/null || true' \
    '  printf "%s\n" orphan-reaped >>"$prefix/reaper-events"' \
    'fi' \
    'printf "%s:%s\n" reaped "$kill_game" >>"$prefix/reaper-events"'
write_script "$TEMP_ROOT/file" \
    '#!/bin/sh' \
    'printf "%s\n" "PE32 executable (GUI) Intel 80386, for MS Windows"'
write_script "$TEMP_ROOT/file64" \
    '#!/bin/sh' \
    'printf "%s\n" "PE32+ executable (GUI) x86-64, for MS Windows"'
write_script "$TEMP_ROOT/wine" \
    '#!/bin/sh' \
    'printf "%s\n" started >>"$WINEPREFIX/wine-events"' \
    'printf "%s\n" "dllpath=$WINEDLLPATH" >>"$WINEPREFIX/wine-events"' \
    'printf "%s\n" "dlloverrides=$WINEDLLOVERRIDES" >>"$WINEPREFIX/wine-events"' \
    'mode=$(cat "$WINEPREFIX/wine-mode")' \
    'case "$mode" in' \
    '  slow-exit) /bin/sleep 1; exit 7 ;;' \
    '  term|term-hang) trap '\''printf "%s\n" term >>"$WINEPREFIX/wine-events"; /bin/sleep 0.2; exit 143'\'' TERM; while :; do /bin/sleep 1; done ;;' \
    '  term-ignore) trap "" TERM; while :; do /bin/sleep 1; done ;;' \
    '  term-orphan) (trap "" TERM; while :; do /bin/sleep 1; done) & printf "%s\n" "$!" >"$WINEPREFIX/orphan.pid"; trap '\''printf "%s\n" term >>"$WINEPREFIX/wine-events"; exit 143'\'' TERM; while :; do /bin/sleep 1; done ;;' \
    '  orphan-exit) /bin/sh -c '\''trap "" TERM; exec -a "$0" /bin/sleep 100'\'' "$1" & printf "%s\n" "$!" >"$WINEPREFIX/orphan.pid"; exit 0 ;;' \
    '  *) exit 0 ;;' \
    'esac'
write_script "$TEMP_ROOT/wineserver" \
    '#!/bin/sh' \
    'printf "%s:%s\n" "${1:-}" "${WINEPREFIX:-unset}" >>"$WINEPREFIX/wineserver-events"' \
    'if [ "${1:-}" = "-w" ] && [ "$(cat "$WINEPREFIX/wine-mode")" = "orphan-exit" ]; then' \
    '  trap '\''exit 0'\'' TERM INT' \
    '  while :; do /bin/sleep 1; done' \
    'fi' \
    'if [ "${1:-}" = "-w" ] && [ "$(cat "$WINEPREFIX/wine-mode")" = "term-hang" ]; then' \
    '  trap '\''printf "%s\\n" wineserver-term >>"$WINEPREFIX/wineserver-events"; exit 0'\'' TERM INT' \
    '  while :; do /bin/sleep 1; done' \
    'fi' \
    'exit 0'

make_case() {
    name=$1
    mode=$2
    arch=${3:-win32}
    case_root=$TEMP_ROOT/$name
    prefix=$case_root/prefix
    wine_root=$case_root/wine
    gptk_root=$case_root/gptk
    bridge_root=$case_root/bridge
    steam_root=$case_root/Steam
    mkdir -p "$prefix" "$wine_root/bin" "$gptk_root/external" \
        "$bridge_root/x86_64-unix" "$bridge_root/i386-windows" \
        "$steam_root/Steam.AppBundle/Steam/Contents/MacOS" "$steam_root/logs" \
        "$case_root/game"
    if [ "$arch" = win64 ]; then
        mkdir -p "$bridge_root/x86_64-windows" \
            "$prefix/drive_c/Program Files (x86)/Steam"
        : >"$bridge_root/x86_64-windows/lsteamclient.dll"
    fi
    cp "$TEMP_ROOT/wine" "$wine_root/bin/wine"
    cp "$TEMP_ROOT/wineserver" "$wine_root/bin/wineserver"
    chmod 755 "$wine_root/bin/wine" "$wine_root/bin/wineserver"
    : >"$prefix/system.reg"
    printf '%s\n' "$mode" >"$prefix/wine-mode"
    : >"$gptk_root/external/libd3dshared.dylib"
    : >"$bridge_root/x86_64-unix/lsteamclient.so"
    : >"$bridge_root/i386-windows/lsteamclient.dll"
    : >"$steam_root/Steam.AppBundle/Steam/Contents/MacOS/steamclient.dylib"
    : >"$steam_root/logs/content_log.txt"
    : >"$case_root/game/test.exe"
    config=$case_root/config
    state_home=$case_root/state
    log=$case_root/bridge.log
    legacy_cloud_marker=$case_root/legacy-cloud-hook-ran
    printf '%s\n' \
        "APP_ID='42'" \
        "GAME_EXE='$case_root/game/test.exe'" \
        "GAME_DIR='$case_root/game'" \
        "PREFIX='$prefix'" \
        "ARCH='$arch'" \
        "STEAM_ROOT='$steam_root'" \
        "WINE_ROOT='$wine_root'" \
        "GPTK_ROOT='$gptk_root'" \
        "BRIDGE_ROOT='$bridge_root'" \
        "STATE_HOME='$state_home'" \
        "FD_EXEC='$TEMP_ROOT/fd-exec'" \
        "REAPER='$TEMP_ROOT/reaper'" \
        "LOG_FILE='$log'" \
        "CLOUD_SYNC_COMMAND='touch $legacy_cloud_marker'" \
        "CLOUD_CDP='1'" \
        "PRESERVE_STEAM_TRANSPORT='0'" \
        "WINE_SESSION_WAIT='1'" \
        "WINE_DEBUG_VALUE='-all'" \
        "WINEMSYNC_VALUE='1'" >"$config"
    CASE_CONFIG=$config
    CASE_LOG=$log
    CASE_RECEIPT=$state_home/sessions/42/last.json
    CASE_PREFIX=$prefix
    CASE_STEAM_LOG=$steam_root/logs/content_log.txt
    CASE_BRIDGE_ROOT=$bridge_root
    CASE_LEGACY_CLOUD_MARKER=$legacy_cloud_marker
}

make_case early-exit slow-exit
set +e
FILE_CMD="$TEMP_ROOT/file" "$ROOT/bin/ullage-bridge" --config "$CASE_CONFIG"
status=$?
set -e
[ "$status" -eq 7 ] || {
    printf 'expected slow game exit 7, got %s\n' "$status" >&2
    exit 1
}
grep -F 'wine_exit=7 signal_received=0' "$CASE_LOG" >/dev/null
[ -f "$CASE_RECEIPT" ]
grep -F '"api_version": 1' "$CASE_RECEIPT" >/dev/null
grep -F '"prefix_clean": true' "$CASE_RECEIPT" >/dev/null
grep -F -- '-w:' "$CASE_PREFIX/wineserver-events" >/dev/null
[ ! -e "$CASE_LEGACY_CLOUD_MARKER" ] || {
    printf '%s\n' 'legacy Cloud hook unexpectedly ran' >&2
    exit 1
}

make_case dllpath slow-exit
mkdir "$CASE_PREFIX/override"
printf '%s\n' "WINEDLLOVERRIDES_VALUE='config-value'" >>"$CASE_CONFIG"
set +e
FILE_CMD="$TEMP_ROOT/file" "$ROOT/bin/ullage-bridge" --config "$CASE_CONFIG" \
    --wine-dllpath "$CASE_PREFIX/override" \
    --wine-dll-overrides 'ddraw=n,b;lsteamclient=b'
status=$?
set -e
[ "$status" -eq 7 ] || {
    printf 'expected dllpath case exit 7, got %s\n' "$status" >&2
    exit 1
}
grep -F "dllpath=$CASE_PREFIX/override" "$CASE_PREFIX/wine-events" >/dev/null
grep -F 'dlloverrides=ddraw=n,b;lsteamclient=b' "$CASE_PREFIX/wine-events" >/dev/null

make_case signal term-hang
set +e
FILE_CMD="$TEMP_ROOT/file" "$ROOT/bin/ullage-bridge" --config "$CASE_CONFIG" &
bridge_pid=$!
ticks=0
while [ ! -f "$CASE_PREFIX/wine-events" ] && [ "$ticks" -lt 40 ]; do
    sleep 0.05
    ticks=$((ticks + 1))
done
[ -f "$CASE_PREFIX/wine-events" ] || {
    printf '%s\n' 'fake Wine did not start before signal test' >&2
    kill -TERM "$bridge_pid" 2>/dev/null || true
    wait "$bridge_pid" 2>/dev/null || true
    exit 1
}
kill -TERM "$bridge_pid"
ticks=0
while [ "$ticks" -lt 100 ]; do
    bridge_state=$(ps -p "$bridge_pid" -o stat= 2>/dev/null | tr -d ' ' || true)
    case "$bridge_state" in ''|Z*) break ;; esac
    sleep 0.05
    ticks=$((ticks + 1))
done
bridge_state=$(ps -p "$bridge_pid" -o stat= 2>/dev/null | tr -d ' ' || true)
case "$bridge_state" in
Z*|'') ;;
*)
    printf '%s\n' 'bridge stayed alive after TERM during session drain' >&2
    ps -axo pid=,ppid=,stat=,command= | awk -v pid="$bridge_pid" '$1 == pid || $2 == pid {print}' >&2 || true
    cat "$CASE_LOG" >&2 || true
    cat "$CASE_PREFIX/wine-events" >&2 || true
    cat "$CASE_PREFIX/wineserver-events" >&2 || true
    kill -KILL "$bridge_pid" 2>/dev/null || true
    wait "$bridge_pid" 2>/dev/null || true
    exit 1
    ;;
esac
wait "$bridge_pid"
status=$?
set -e
[ "$status" -eq 143 ] || {
    printf 'expected TERM exit 143, got %s\n' "$status" >&2
    exit 1
}
grep -F 'term' "$CASE_PREFIX/wine-events" >/dev/null
grep -F 'wine_exit=143 signal_received=1' "$CASE_LOG" >/dev/null

make_case forced-stop term-ignore
set +e
FILE_CMD="$TEMP_ROOT/file" "$ROOT/bin/ullage-bridge" --config "$CASE_CONFIG" \
    2>"$CASE_PREFIX/bridge-stderr" &
bridge_pid=$!
ticks=0
while [ ! -f "$CASE_PREFIX/wine-events" ] && [ "$ticks" -lt 40 ]; do
    sleep 0.05
    ticks=$((ticks + 1))
done
[ -f "$CASE_PREFIX/wine-events" ] || {
    printf '%s\n' 'fake Wine did not start before forced-stop test' >&2
    kill -KILL "$bridge_pid" 2>/dev/null || true
    wait "$bridge_pid" 2>/dev/null || true
    exit 1
}
kill -TERM "$bridge_pid"
ticks=0
while [ "$ticks" -lt 120 ]; do
    bridge_state=$(ps -p "$bridge_pid" -o stat= 2>/dev/null | tr -d ' ' || true)
    case "$bridge_state" in ''|Z*) break ;; esac
    sleep 0.05
    ticks=$((ticks + 1))
done
bridge_state=$(ps -p "$bridge_pid" -o stat= 2>/dev/null | tr -d ' ' || true)
case "$bridge_state" in
Z*|'') ;;
*)
    printf '%s\n' 'bridge did not force-reap a TERM-ignoring launcher' >&2
    kill -KILL "$bridge_pid" 2>/dev/null || true
    wait "$bridge_pid" 2>/dev/null || true
    exit 1
    ;;
esac
wait "$bridge_pid"
status=$?
set -e
[ "$status" -eq 137 ] || {
    printf 'expected forced-stop exit 137, got %s\n' "$status" >&2
    exit 1
}
grep -F 'reaped:1' "$CASE_PREFIX/reaper-events" >/dev/null
grep -F 'wine_exit=137 signal_received=1' "$CASE_LOG" >/dev/null

make_case orphan term-orphan
set +e
FILE_CMD="$TEMP_ROOT/file" "$ROOT/bin/ullage-bridge" --config "$CASE_CONFIG" &
bridge_pid=$!
ticks=0
while [ ! -f "$CASE_PREFIX/orphan.pid" ] && [ "$ticks" -lt 40 ]; do
    sleep 0.05
    ticks=$((ticks + 1))
done
[ -f "$CASE_PREFIX/orphan.pid" ] || {
    printf '%s\n' 'fake Wine did not create orphan before cleanup test' >&2
    kill -TERM "$bridge_pid" 2>/dev/null || true
    wait "$bridge_pid" 2>/dev/null || true
    exit 1
}
orphan_pid=$(cat "$CASE_PREFIX/orphan.pid")
kill -TERM "$bridge_pid"
wait "$bridge_pid"
status=$?
set -e
[ "$status" -eq 143 ] || {
    printf 'expected orphan case exit 143, got %s\n' "$status" >&2
    exit 1
}
sleep 0.2
if kill -0 "$orphan_pid" 2>/dev/null; then
    printf '%s\n' 'prefix-scoped game reaper left an orphan alive' >&2
    kill -KILL "$orphan_pid" 2>/dev/null || true
    exit 1
fi
grep -F 'orphan-reaped' "$CASE_PREFIX/reaper-events" >/dev/null
grep -F 'reaped:1' "$CASE_PREFIX/reaper-events" >/dev/null
grep -F 'wine_exit=143 signal_received=1' "$CASE_LOG" >/dev/null

make_case steam-stop term
set +e
FILE_CMD="$TEMP_ROOT/file" "$ROOT/bin/ullage-bridge" --config "$CASE_CONFIG" &
bridge_pid=$!
ticks=0
while [ ! -f "$CASE_PREFIX/wine-events" ] && [ "$ticks" -lt 40 ]; do
    sleep 0.05
    ticks=$((ticks + 1))
done
[ -f "$CASE_PREFIX/wine-events" ] || {
    echo 'fake Wine did not start before Steam stop test' >&2
    kill -TERM "$bridge_pid" 2>/dev/null || true
    wait "$bridge_pid" 2>/dev/null || true
    exit 1
}
echo '[2026-08-25 00:00:00] AppID 142 state changed : Fully Installed,App Running,Terminating,' >>"$CASE_STEAM_LOG"
sleep 0.2
bridge_state=$(ps -p "$bridge_pid" -o stat= 2>/dev/null | tr -d ' ' || true)
case "$bridge_state" in
Z*|'')
    echo 'bridge matched a different AppID termination event' >&2
    kill -KILL "$bridge_pid" 2>/dev/null || true
    wait "$bridge_pid" 2>/dev/null || true
    exit 1
    ;;
esac
echo '[2026-08-25 00:00:01] AppID 42 state changed : Fully Installed,App Running,Terminating,' >>"$CASE_STEAM_LOG"
ticks=0
while [ "$ticks" -lt 100 ]; do
    bridge_state=$(ps -p "$bridge_pid" -o stat= 2>/dev/null | tr -d ' ' || true)
    case "$bridge_state" in ''|Z*) break ;; esac
    sleep 0.05
    ticks=$((ticks + 1))
done
bridge_state=$(ps -p "$bridge_pid" -o stat= 2>/dev/null | tr -d ' ' || true)
case "$bridge_state" in
Z*|'') ;;
*)
    echo 'bridge ignored Steam Terminating state' >&2
    cat "$CASE_LOG" >&2 || true
    kill -KILL "$bridge_pid" 2>/dev/null || true
    wait "$bridge_pid" 2>/dev/null || true
    exit 1
    ;;
esac
wait "$bridge_pid"
status=$?
set -e
[ "$status" -eq 143 ] || {
    echo "expected Steam stop exit 143, got $status" >&2
    exit 1
}
grep -F 'term' "$CASE_PREFIX/wine-events" >/dev/null
grep -F 'wine_exit=143 signal_received=1' "$CASE_LOG" >/dev/null
grep -F 'native Steam requested stop for appid=42' "$CASE_LOG" >/dev/null

make_case steam-stop-after-launch orphan-exit
set +e
FILE_CMD="$TEMP_ROOT/file" "$ROOT/bin/ullage-bridge" --config "$CASE_CONFIG" &
bridge_pid=$!
ticks=0
while [ ! -f "$CASE_PREFIX/orphan.pid" ] && [ "$ticks" -lt 40 ]; do
    sleep 0.05
    ticks=$((ticks + 1))
done
[ -f "$CASE_PREFIX/orphan.pid" ] || {
    echo 'fake Wine did not create post-launch orphan before Steam stop test' >&2
    kill -TERM "$bridge_pid" 2>/dev/null || true
    wait "$bridge_pid" 2>/dev/null || true
    exit 1
}
ticks=0
while ! grep -F -- '-w:' "$CASE_PREFIX/wineserver-events" >/dev/null 2>&1 &&
    [ "$ticks" -lt 40 ]; do
    sleep 0.05
    ticks=$((ticks + 1))
done
sleep 0.2
echo '[2026-08-25 00:00:00] AppID 42 state changed : Fully Installed,App Running,Terminating,' >>"$CASE_STEAM_LOG"
ticks=0
while [ "$ticks" -lt 100 ]; do
    bridge_state=$(ps -p "$bridge_pid" -o stat= 2>/dev/null | tr -d ' ' || true)
    case "$bridge_state" in ''|Z*) break ;; esac
    sleep 0.05
    ticks=$((ticks + 1))
done
bridge_state=$(ps -p "$bridge_pid" -o stat= 2>/dev/null | tr -d ' ' || true)
case "$bridge_state" in
Z*|'') ;;
*)
    echo 'bridge did not watch Steam while draining a post-launch orphan' >&2
    cat "$CASE_LOG" >&2 || true
    kill -KILL "$bridge_pid" 2>/dev/null || true
    wait "$bridge_pid" 2>/dev/null || true
    exit 1
    ;;
esac
wait "$bridge_pid"
status=$?
set -e
[ "$status" -eq 0 ] || {
    echo "expected post-launch Steam stop to preserve clean launcher exit, got $status" >&2
    exit 1
}
orphan_pid=$(cat "$CASE_PREFIX/orphan.pid")
sleep 0.2
if kill -0 "$orphan_pid" 2>/dev/null; then
    echo 'post-launch Steam stop left an orphan alive' >&2
    kill -KILL "$orphan_pid" 2>/dev/null || true
    exit 1
fi
grep -F 'orphan-reaped' "$CASE_PREFIX/reaper-events" >/dev/null
grep -F 'reaped:1' "$CASE_PREFIX/reaper-events" >/dev/null
grep -F 'native Steam requested stop for appid=42' "$CASE_LOG" >/dev/null
grep -F 'wine_exit=0 signal_received=1' "$CASE_LOG" >/dev/null

make_case x64-forwarder slow-exit win64
printf '%s\n' forwarder >"$CASE_BRIDGE_ROOT/x86_64-windows/steamclient64.dll"
printf '%s\n' stale >"$CASE_PREFIX/drive_c/Program Files (x86)/Steam/steamclient64.dll"
set +e
forwarder_error=$(
    FILE_CMD="$TEMP_ROOT/file64" "$ROOT/bin/ullage-bridge" --config "$CASE_CONFIG" 2>&1
)
status=$?
set -e
[ "$status" -ne 0 ] || {
    printf '%s\n' 'expected stale x64 forwarder to be rejected' >&2
    exit 1
}
case "$forwarder_error" in
    *'staged steamclient64.dll does not match'*) ;;
    *)
        printf '%s\n' "$forwarder_error" >&2
        exit 1
        ;;
esac
cp "$CASE_BRIDGE_ROOT/x86_64-windows/steamclient64.dll" \
    "$CASE_PREFIX/drive_c/Program Files (x86)/Steam/steamclient64.dll"
set +e
FILE_CMD="$TEMP_ROOT/file64" "$ROOT/bin/ullage-bridge" --config "$CASE_CONFIG"
status=$?
set -e
[ "$status" -eq 7 ] || {
    printf 'expected x64 forwarder case exit 7, got %s\n' "$status" >&2
    exit 1
}
grep -F 'wine_exit=7 signal_received=0' "$CASE_LOG" >/dev/null

echo 'steamclient64 forwarder validation: ok'

echo 'bridge supervision and Steam stop: ok'
