"""Build a standalone KeyVault executable with PyInstaller.

PyInstaller cannot cross compile. Run the script on the operating system
that matches --target. The ccrypt binary found on PATH is bundled so the
executable does not depend on a system ccrypt. git must still be installed.
"""

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT : Path = Path( __file__ ).resolve().parent.parent
ENTRY_POINT : Path = PROJECT_ROOT / "src" / "keyvault" / "__main__.py"
DIST_DIR : Path = PROJECT_ROOT / "dist"
BUILD_DIR : Path = PROJECT_ROOT / "build"
HOST_TARGETS : dict[str, str] = { "Linux": "linux", "Windows": "windows" }


def detect_host_target() -> str:
  """Return `linux` or `windows` for the running system."""

  system : str = platform.system()

  if system not in HOST_TARGETS:
    sys.exit( f"build: unsupported host system {system}" )

  return HOST_TARGETS[ system ]


def find_ccrypt_binary(
  target_ : str ,
) -> Optional[Path]:
  """Return the ccrypt executable on PATH or None when missing."""

  found : Optional[str] = shutil.which(
    "ccrypt.exe" if target_ == "windows" else "ccrypt"
  )

  return Path( found ) if found else None


def build_command(
  target_ : str ,
  ccrypt_ : Optional[Path] ,
) -> list[str]:
  """
  Assemble the PyInstaller command line.

  Args:
    target_ (str): `linux` or `windows`.
    ccrypt_ (Path, optional): ccrypt binary to embed.

  Returns:
    list[str]: Command ready for subprocess.
  """

  assert target_ in ( "linux", "windows" ), "unknown target"

  separator : str = ";" if target_ == "windows" else ":"
  command : list[str] = [
    "uv", "run", "pyinstaller",
    "--noconfirm", "--clean", "--onefile",
    "--name", f"keyvault-{target_}",
    "--paths", str( PROJECT_ROOT / "src" ),
    "--collect-all", "textual",
    "--distpath", str( DIST_DIR ),
    "--workpath", str( BUILD_DIR ),
    "--specpath", str( BUILD_DIR ),
  ]

  if ccrypt_ is not None:
    command += [ "--add-binary", f"{ccrypt_}{separator}." ]

  return command + [ str( ENTRY_POINT ) ]


def main() -> None:
  """Parse arguments and run PyInstaller."""

  parser : argparse.ArgumentParser = argparse.ArgumentParser(
    description="Build a standalone KeyVault executable."
  )
  parser.add_argument(
    "--target",
    choices=[ "linux", "windows" ],
    default=detect_host_target(),
    help="must match the host operating system",
  )
  arguments : argparse.Namespace = parser.parse_args()

  if arguments.target != detect_host_target():
    sys.exit(
      f"build: --target {arguments.target} must run on a "
      f"{arguments.target} host. PyInstaller does not cross compile."
    )

  ccrypt : Optional[Path] = find_ccrypt_binary( arguments.target )
  if ccrypt is None:
    print( "build: ccrypt not found on PATH. The binary will not be bundled." )

  subprocess.run(
    build_command( arguments.target, ccrypt ), cwd=PROJECT_ROOT, check=True
  )
  print( f"build: executable written to {DIST_DIR}" )


if __name__ == "__main__":
  main()
