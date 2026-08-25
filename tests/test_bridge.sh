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
    'while [ "$#" -gt 0 ]; do' \
    '  if [ "$1" = "--prefix" ]; then prefix=$2; shift 2; else shift; fi' \
    'done' \
    'printf "%s\n" reaped >>"$prefix/reaper-events"'
write_script "$TEMP_ROOT/file" \
    '#!/bin/sh' \
    'printf "%s\n" "PE32 executable (GUI) Intel 80386, for MS Windows"'
write_script "$TEMP_ROOT/wine" \
    '#!/bin/sh' \
    'printf "%s\n" started >>"$WINEPREFIX/wine-events"' \
    'mode=$(cat "$WINEPREFIX/wine-mode")' \
    'case "$mode" in' \
    '  slow-exit) /bin/sleep 1; exit 7 ;;' \
    '  term) trap '\''printf "%s\n" term >>"$WINEPREFIX/wine-events"; exit 143'\'' TERM; while :; do /bin/sleep 1; done ;;' \
    '  *) exit 0 ;;' \
    'esac'
write_script "$TEMP_ROOT/wineserver" \
    '#!/bin/sh' \
    'printf "%s:%s\n" "${1:-}" "${WINEPREFIX:-unset}" >>"$WINEPREFIX/wineserver-events"' \
    'exit 0'

make_case() {
    name=$1
    mode=$2
    case_root=$TEMP_ROOT/$name
    prefix=$case_root/prefix
    wine_root=$case_root/wine
    gptk_root=$case_root/gptk
    bridge_root=$case_root/bridge
    steam_root=$case_root/Steam
    mkdir -p "$prefix" "$wine_root/bin" "$gptk_root/external" \
        "$bridge_root/x86_64-unix" "$bridge_root/i386-windows" \
        "$steam_root/Steam.AppBundle/Steam/Contents/MacOS" "$case_root/game"
    cp "$TEMP_ROOT/wine" "$wine_root/bin/wine"
    cp "$TEMP_ROOT/wineserver" "$wine_root/bin/wineserver"
    chmod 755 "$wine_root/bin/wine" "$wine_root/bin/wineserver"
    : >"$prefix/system.reg"
    printf '%s\n' "$mode" >"$prefix/wine-mode"
    : >"$gptk_root/external/libd3dshared.dylib"
    : >"$bridge_root/x86_64-unix/lsteamclient.so"
    : >"$bridge_root/i386-windows/lsteamclient.dll"
    : >"$steam_root/Steam.AppBundle/Steam/Contents/MacOS/steamclient.dylib"
    : >"$case_root/game/test.exe"
    config=$case_root/config
    log=$case_root/bridge.log
    printf '%s\n' \
        "APP_ID='42'" \
        "GAME_EXE='$case_root/game/test.exe'" \
        "GAME_DIR='$case_root/game'" \
        "PREFIX='$prefix'" \
        "ARCH='win32'" \
        "STEAM_ROOT='$steam_root'" \
        "WINE_ROOT='$wine_root'" \
        "GPTK_ROOT='$gptk_root'" \
        "BRIDGE_ROOT='$bridge_root'" \
        "FD_EXEC='$TEMP_ROOT/fd-exec'" \
        "REAPER='$TEMP_ROOT/reaper'" \
        "LOG_FILE='$log'" \
        "PRESERVE_STEAM_TRANSPORT='0'" \
        "WINE_SESSION_WAIT='1'" \
        "WINE_DEBUG_VALUE='-all'" \
        "WINEMSYNC_VALUE='1'" >"$config"
    CASE_CONFIG=$config
    CASE_LOG=$log
    CASE_PREFIX=$prefix
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
grep -F -- '-w:' "$CASE_PREFIX/wineserver-events" >/dev/null

make_case signal term
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
wait "$bridge_pid"
status=$?
set -e
[ "$status" -eq 143 ] || {
    printf 'expected TERM exit 143, got %s\n' "$status" >&2
    exit 1
}
grep -F 'term' "$CASE_PREFIX/wine-events" >/dev/null
grep -F 'wine_exit=143 signal_received=1' "$CASE_LOG" >/dev/null

printf '%s\n' 'bridge supervision races: ok'
