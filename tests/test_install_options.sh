#!/bin/sh
set -eu

ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
INSTALL="$ROOT/bin/ullage-install"

expect_native_conflict() {
    set +e
    output=$(
        "$INSTALL" \
            --appid 1 \
            --target /tmp/ullage-test-missing.exe \
            --cloud-native \
            "$@" 2>&1
    )
    status=$?
    set -e
    [ "$status" -eq 2 ]
    case "$output" in
        *"cannot be combined"*) ;;
        *)
            printf '%s\n' "$output" >&2
            return 1
            ;;
    esac
}

expect_native_conflict --cloud-cdp
expect_native_conflict --cloud-sync-command true

case "$("$INSTALL" --help 2>&1)" in
    *"--wine-dllpath PATHS"*) ;;
    *) printf '%s\n' 'installer missing --wine-dllpath' >&2; exit 1 ;;
esac
case "$("$ROOT/bin/ullage-bridge" --help 2>&1)" in
    *"--wine-dllpath PATHS"*) ;;
    *) printf '%s\n' 'bridge missing --wine-dllpath' >&2; exit 1 ;;
esac
printf '%s\n' 'install option conflicts: ok'
