"""User configuration: last opened folder and terminal color palette."""

import json
import os
import tomllib
from pathlib import Path
from typing import Optional

APP_DIR_NAME : str = "keyvault"

DEFAULT_PALETTE : dict[str, str] = {
  "background": "#1e1e2e",
  "foreground": "#cdd6f4",
  "muted": "#6c7086",
  "red": "#f38ba8",
  "green": "#a6e3a1",
  "yellow": "#f9e2af",
  "blue": "#89b4fa",
  "magenta": "#cba6f7",
  "cyan": "#94e2d5",
}


def config_dir() -> Path:
  """Return the XDG config directory of the application."""

  base : str = os.environ.get(
    "XDG_CONFIG_HOME", str( Path.home() / ".config" )
  )

  return Path( base ) / APP_DIR_NAME


def load_palette(
  palette_file_ : Optional[Path] = None ,
) -> dict[str, str]:
  """
  Merge palette.toml over the default palette.

  Unknown keys and values that are not `#rrggbb` strings are ignored.

  Args:
    palette_file_ (Path, optional): TOML file. Defaults to the config dir.

  Returns:
    dict[str, str]: Palette with every default key present.
  """

  path : Path = palette_file_ or ( config_dir() / "palette.toml" )
  palette : dict[str, str] = DEFAULT_PALETTE.copy()

  if not path.is_file():
    return palette

  try:
    loaded : dict = tomllib.loads( path.read_text() )
  except ( tomllib.TOMLDecodeError, OSError ):
    return palette

  for key, value in loaded.items():
    is_hex : bool = (
      isinstance( value, str )
      and len( value ) == 7
      and value.startswith( "#" )
      and all( c in "0123456789abcdefABCDEF" for c in value[ 1: ] )
    )
    if key in palette and is_hex:
      palette[ key ] = value

  assert set( palette ) == set( DEFAULT_PALETTE ), "palette keys changed"

  return palette


def load_last_folder() -> Optional[Path]:
  """Return the last opened folder when it still exists."""

  state_file : Path = config_dir() / "state.json"

  try:
    folder : Path = Path( json.loads( state_file.read_text() )[ "folder" ] )
  except ( OSError, ValueError, KeyError, TypeError ):
    return None

  return folder if folder.is_dir() else None


def save_last_folder(
  folder_ : Path ,
) -> None:
  """Persist folder_ as the last opened folder. Failures are ignored."""

  try:
    config_dir().mkdir( parents=True, exist_ok=True )
    ( config_dir() / "state.json" ).write_text(
      json.dumps( { "folder": str( folder_ ) } )
    )
  except OSError:
    pass


# ==============================================================================
# Unittest
if __name__ == "__main__":
  assert load_palette( Path( "/nonexistent.toml" ) ) == DEFAULT_PALETTE
  print( "config self test passed" )
