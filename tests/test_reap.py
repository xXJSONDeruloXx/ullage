#!/usr/bin/env python3
"""Guard the Windows command-line parsing and scope checks used by the reaper."""

import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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
assert '"$LSOF" -a -p "$process_id" -d txt -Fn' in source
assert 'has_open_path "$process_id" "$GAME_ROOT"' in source[
    live_start : source.index("stop_wineserver()")
]
assert 'has_open_text "$process_id" "$PREFIX"' in source[
    live_start : source.index("stop_wineserver()")
]
assert 'case "$process_name" in' in source[live_start : source.index("stop_wineserver()")]
assert '*.exe)' in source[live_start : source.index("stop_wineserver()")]
assert 'is_helper_name "$process_name" && continue' in source[
    game_start : source.index("is_live_game_process()")
]
assert "popcap" not in source.lower()


def test_reparented_executable() -> None:
    """A prefix-resident unpacked executable is still a game process."""
    compiler = shutil.which("clang")
    assert compiler is not None, "clang is required for the reaper process test"
    with tempfile.TemporaryDirectory(prefix="ullage-reap-test-") as directory:
        root = Path(directory)
        prefix = root / "prefix"
        game_root = root / "game"
        prefix.mkdir()
        game_root.mkdir()
        helper_source = root / "sleeper.c"
        helper_source.write_text(
            "#include <unistd.h>\n"
            "int main(void) { for (;;) pause(); }\n",
            encoding="utf-8",
        )
        executable = prefix / "one screen.exe"
        subprocess.run(
            [compiler, "-O2", "-Wall", "-Wextra", "-Werror", "-o", executable, helper_source],
            check=True,
            capture_output=True,
            text=True,
        )
        child = subprocess.Popen([executable], cwd=prefix)
        try:
            result = subprocess.run(
                [
                    str(ROOT / "bin" / "ullage-reap"),
                    "--prefix",
                    str(prefix),
                    "--wineserver",
                    "/usr/bin/true",
                    "--game-root",
                    str(game_root),
                    "--kill-game-processes",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            assert "reaped_game_pids=" in result.stdout
            assert child.wait(timeout=2) is not None
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()


test_reparented_executable()
print("reaper command parsing and extracted-child scope: ok")
