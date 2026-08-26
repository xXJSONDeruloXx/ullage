#!/bin/sh
set -eu

ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
INSTALL="$ROOT/bin/ullage-install"

INSTALL_HELP=$("$INSTALL" --help 2>&1)
BRIDGE_HELP=$("$ROOT/bin/ullage-bridge" --help 2>&1)

expect_removed() {
    command_path=$1
    option=$2
    set +e
    output=$("$command_path" "$option" 2>&1)
    status=$?
    set -e
    [ "$status" -eq 2 ] || {
        printf 'removed option unexpectedly succeeded: %s\n%s\n' "$option" "$output" >&2
        exit 1
    }
    case "$output" in
        *"unknown option"*) ;;
        *)
            printf 'removed option did not report unknown option: %s\n%s\n' \
                "$option" "$output" >&2
            exit 1
            ;;
    esac
}

case "$INSTALL_HELP" in
    *"--wine-dllpath PATHS"*) ;;
    *) printf '%s\n' 'installer missing --wine-dllpath' >&2; exit 1 ;;
esac
case "$BRIDGE_HELP" in
    *"--wine-dllpath PATHS"*) ;;
    *) printf '%s\n' 'bridge missing --wine-dllpath' >&2; exit 1 ;;
esac
case "$INSTALL_HELP" in
    *"--wine-dll-overrides VALUE"*) ;;
    *) printf '%s\n' 'installer missing --wine-dll-overrides' >&2; exit 1 ;;
esac
case "$BRIDGE_HELP" in
    *"--wine-dll-overrides VALUE"*) ;;
    *) printf '%s\n' 'bridge missing --wine-dll-overrides' >&2; exit 1 ;;
esac
case "$INSTALL_HELP" in
    *"--steamclient64-forwarder PATH"*) ;;
    *) printf '%s\n' 'installer missing --steamclient64-forwarder' >&2; exit 1 ;;
esac
case "$BRIDGE_HELP" in
    *"--steamclient64-forwarder PATH"*) ;;
    *) printf '%s\n' 'bridge missing --steamclient64-forwarder' >&2; exit 1 ;;
esac
case "$INSTALL_HELP" in
    *"--cloud-native"*) ;;
    *) printf '%s\n' 'installer missing --cloud-native' >&2; exit 1 ;;
esac
case "$INSTALL_HELP" in
    *"--cloud-steam3-account-id ID"*) ;;
    *) printf '%s\n' 'installer missing native Cloud seed account option' >&2; exit 1 ;;
esac
case "$INSTALL_HELP" in
    *"--cloud-steam-account-name NAME"*) ;;
    *) printf '%s\n' 'installer missing SteamCloudDocuments account option' >&2; exit 1 ;;
esac
case "$INSTALL_HELP$BRIDGE_HELP" in
    *"--cloud-sync-command"*|*"--cloud-cdp"*)
        printf '%s\n' 'external Cloud fallback options remain exposed' >&2
        exit 1
        ;;
esac
expect_removed "$INSTALL" --cloud-cdp
expect_removed "$ROOT/bin/ullage-bridge" --cloud-cdp
expect_removed "$INSTALL" --cloud-sync-command
expect_removed "$ROOT/bin/ullage-bridge" --cloud-sync-command
printf '%s\n' 'install options: ok'
