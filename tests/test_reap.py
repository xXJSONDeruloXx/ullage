#!/usr/bin/env python3
"""Guard the Windows command-line parsing used by the prefix reaper."""

from pathlib import Path


source = (Path(__file__).resolve().parents[1] / "bin" / "ullage-reap").read_text(
    encoding="utf-8"
)

# Wine reports helpers as e.g. ``C:\\windows\\system32\\explorer.exe /desktop``.
# Arguments must be removed before slash/backslash basename extraction, or the
# final argument ("desktop") is mistaken for the process name.
assert source.count("process_command=${process_command%% *}") == 2
assert source.count("process_name=${process_command##*/}") == 2
assert source.count("process_name=${process_name##*\\\\}") == 2
for start in (source.index("is_live_helper()"), source.index("list_helpers()")):
    command_start = source.index("process_command=${process_command%% *}", start)
    slash_start = source.index("process_name=${process_command##*/}", start)
    backslash_start = source.index("process_name=${process_name##*\\\\}", start)
    assert command_start < slash_start < backslash_start

print("reaper command parsing: ok")
