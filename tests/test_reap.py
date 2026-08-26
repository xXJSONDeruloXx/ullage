#!/usr/bin/env python3
"""Guard the Windows command-line parsing used by the prefix reaper."""

from pathlib import Path


source = (Path(__file__).resolve().parents[1] / "bin" / "ullage-reap").read_text(
    encoding="utf-8"
)

# Wine reports helpers as e.g. ``C:\\windows\\system32\\explorer.exe /desktop``.
# Arguments must be removed before slash/backslash basename extraction, or the
# final argument ("desktop") is mistaken for the process name.
parser_start = source.index("process_name_from_command()")
assert "process_executable=${process_command%%.[Ee][Xx][Ee]*}.exe" in source[parser_start:]
assert "process_name=${process_executable##*/}" in source[parser_start:]
assert "process_name=${process_name##*\\\\}" in source[parser_start:]
assert source.count('process_name=$(process_name_from_command "$process_command")') == 4
assert "GAME_ROOT=$(CDPATH= cd \"$GAME_ROOT\" && pwd -P)" in source
assert "PREFIX=$(CDPATH= cd \"$PREFIX\" && pwd -P)" in source

# A spawned game may be reparented to PID 1 and lose the Z: install path from
# its command line. Discovery must therefore validate the prefix and use the
# physical install root from lsof as a fallback association.
game_start = source.index("list_game_processes()")
live_start = source.index("is_live_game_process()")
assert source.index("is_live_game_process \"$process_id\"", game_start) < source.index(
    "done <<EOF", game_start
)
assert 'case "$process_command" in' in source[parser_start : source.index("stop_wineserver()")]
assert '"$GAME_ROOT"' in source[live_start : source.index("stop_wineserver()")]
assert '"$LSOF" -a -p "$process_id" -Fn' in source
assert 'has_open_path "$process_id" "$GAME_ROOT"' in source[
    live_start : source.index("stop_wineserver()")
]
assert 'case "$process_name" in' in source[live_start : source.index("stop_wineserver()")]
assert '*.exe)' in source[live_start : source.index("stop_wineserver()")]
assert 'is_helper_name "$process_name" && continue' in source[
    game_start : source.index("is_live_game_process()")
]
assert "popcap" not in source.lower()

print("reaper command parsing: ok")
