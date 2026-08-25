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
printf '%s\n' 'install option conflicts: ok'
