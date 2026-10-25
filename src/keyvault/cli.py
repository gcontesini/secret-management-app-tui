"""Command line entry point."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from keyvault import __version__
from keyvault.app import Key_Vault_App
from keyvault.config import load_last_folder
from keyvault.crypto import Crypto_Error, find_ccrypt


def parse_arguments(
  argv_ : Optional[list[str]] = None ,
) -> argparse.Namespace:
  """
  Parse command line arguments.

  Args:
    argv_ (list[str], optional): Arguments without the program name.

  Returns:
    argparse.Namespace: Parsed arguments with `folder` as Path or None.
  """

  parser : argparse.ArgumentParser = argparse.ArgumentParser(
    prog="keyvault",
    description="Terminal manager for ccrypt encrypted secret files.",
  )
  parser.add_argument(
    "folder",
    nargs="?",
    type=Path,
    default=None,
    help="folder with the secrets. Defaults to the last opened folder.",
  )
  parser.add_argument(
    "--version", action="version", version=f"keyvault {__version__}"
  )

  return parser.parse_args( argv_ )


def run(
  argv_ : Optional[list[str]] = None ,
) -> None:
  """Start the TUI after checking that ccrypt is available."""

  arguments : argparse.Namespace = parse_arguments( argv_ )

  try:
    find_ccrypt()
  except Crypto_Error as error:
    sys.exit( f"keyvault: {error}" )

  folder : Optional[Path] = arguments.folder
  if folder is not None:
    folder = folder.expanduser()
    if not folder.is_dir():
      sys.exit( f"keyvault: {folder} is not a folder" )
  else:
    folder = load_last_folder()

  Key_Vault_App( folder_=folder ).run()


if __name__ == "__main__":
  run()
