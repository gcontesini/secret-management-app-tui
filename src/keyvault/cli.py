"""Command line entry point."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from keyvault import __version__
from keyvault.app import Key_Vault_App
from keyvault.config import load_last_folder
from keyvault.crypto import BACKENDS, Crypto_Error, find_ccrypt, find_rage


def parse_arguments(
  argv_ : Optional[list[str]] = None ,
) -> argparse.Namespace:
  """
  Parse command line arguments.

  Args:
    argv_ (list[str], optional): Arguments without the program name.

  Returns:
    argparse.Namespace: Parsed arguments with `folder` as Path or None and
      `backend` as str or None.
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
    "--backend",
    choices=BACKENDS,
    default=None,
    help="encryption backend for new files. Defaults to the last used one.",
  )
  parser.add_argument(
    "--version", action="version", version=f"keyvault {__version__}"
  )

  return parser.parse_args( argv_ )


def run(
  argv_ : Optional[list[str]] = None ,
) -> None:
  """
  Start the TUI after checking that the backend tool is available.

  `export` lines queued by the Export dialog are printed to stdout after the
  TUI closes so that `eval "$(keyvault)"` applies them to the calling shell.
  """

  arguments : argparse.Namespace = parse_arguments( argv_ )

  try:
    find_rage() if arguments.backend == "rage" else find_ccrypt()
  except Crypto_Error as error:
    sys.exit( f"keyvault: {error}" )

  folder : Optional[Path] = arguments.folder
  if folder is not None:
    folder = folder.expanduser()
    if not folder.is_dir():
      sys.exit( f"keyvault: {folder} is not a folder" )
  else:
    folder = load_last_folder()

  app : Key_Vault_App = Key_Vault_App(
    folder_=folder, backend_=arguments.backend
  )
  app.run()

  for line in app.pending_exports:
    print( line )


if __name__ == "__main__":
  run()
