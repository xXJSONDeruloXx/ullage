"""Test Windows Auto Cloud roots map into the Wine prefix."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("ullage_cloud_path", ROOT / "bin/ullage-cloud-path.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

prefix = ROOT / "tmp-prefix"
assert MODULE.resolve(prefix, "kurt", "WinAppDataLocal", r"BANDAI\save.dat") == (
    prefix / "drive_c/users/kurt/AppData/Local/BANDAI/save.dat"
).resolve()
assert MODULE.resolve(prefix, "kurt", "WinAppDataLocalLow", "Game/save.dat") == (
    prefix / "drive_c/users/kurt/AppData/LocalLow/Game/save.dat"
).resolve()
assert MODULE.resolve(prefix, "kurt", "WindowsHome", "Documents/Stellar/save.dat") == (
    prefix / "drive_c/users/kurt/Documents/Stellar/save.dat"
).resolve()
assert MODULE.resolve(prefix, "kurt", "WinProgramData", "Vendor/state") == (
    prefix / "drive_c/ProgramData/Vendor/state"
).resolve()
install_dir = prefix / "steamapps/common/Example Game"
assert MODULE.resolve(
    prefix,
    "kurt",
    "gameinstall",
    "saves/slot.dat",
    install_dir,
) == (install_dir / "saves/slot.dat").resolve()
assert MODULE.resolve(
    prefix,
    "kurt",
    "SteamCloudDocuments",
    "SavesDir/slot.sav",
    install_dir,
    "account-name",
) == (
    prefix
    / "drive_c/users/kurt/Documents/Steam Cloud/account-name/Example Game/SavesDir/slot.sav"
).resolve()

try:
    MODULE.resolve(prefix, "kurt", "WinAppDataLocal", "../../outside")
except ValueError:
    pass
else:
    raise AssertionError("cloud path escape was accepted")

try:
    MODULE.resolve(prefix, "kurt", "SteamCloudDocuments", "save.dat", install_dir)
except ValueError:
    pass
else:
    raise AssertionError("SteamCloudDocuments accepted a missing account name")

print("cloud path resolution: ok")
