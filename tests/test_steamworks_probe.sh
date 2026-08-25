#!/bin/sh
# Compile the optional Steamworks probe when MinGW is available locally.
set -eu

ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/ullage-probe-test.XXXXXX")
trap 'rm -rf "$TEMP_ROOT"' EXIT HUP INT TERM

X64_CC=$(command -v x86_64-w64-mingw32-gcc || true)
X86_CC=$(command -v i686-w64-mingw32-gcc || true)
if [ -z "$X64_CC" ] || [ -z "$X86_CC" ]; then
    echo 'steamworks probe compile: skipped (MinGW unavailable)'
    exit 0
fi

"$X64_CC" -O2 -Wall -Wextra -Werror \
    -o "$TEMP_ROOT/probe64.exe" "$ROOT/tools/ullage-steamworks-probe.c"
"$X86_CC" -O2 -Wall -Wextra -Werror \
    -o "$TEMP_ROOT/probe32.exe" "$ROOT/tools/ullage-steamworks-probe.c"

case "$(/usr/bin/file -b "$TEMP_ROOT/probe64.exe")" in
    *'PE32+'*) ;;
    *) echo '64-bit Steamworks probe is not a PE32+ executable' >&2; exit 1 ;;
esac
case "$(/usr/bin/file -b "$TEMP_ROOT/probe32.exe")" in
    *'PE32 executable'*) ;;
    *) echo '32-bit Steamworks probe is not a PE32 executable' >&2; exit 1 ;;
esac

echo 'steamworks probe compile: ok'
