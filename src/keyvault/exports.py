"""Format decrypted secrets as `.env` lines or bash `export` commands."""

import os
import re
import shlex
from pathlib import Path

ENV_FILE_NAME : str = ".env"
VARIABLE_PATTERN : re.Pattern = re.compile( r"[A-Za-z_][A-Za-z0-9_]*" )


class Export_Error( Exception ):
  """Raised for an invalid variable name or an unwritable `.env` file."""


def validate_variable_name(
  name_ : str ,
) -> str:
  """
  Validate a shell variable name.

  Args:
    name_ (str): Raw name typed by the user.

  Returns:
    str: Stripped name.

  Raises:
    Export_Error: If the name is not a valid shell identifier.
  """

  name : str = name_.strip()

  if VARIABLE_PATTERN.fullmatch( name ) is None:
    raise Export_Error(
      f"{name_!r} is not a valid name. Use letters and digits and `_`."
    )

  return name


def format_export_line(
  name_ : str ,
  value_ : str ,
) -> str:
  """Return `export name='value'` quoted for bash."""

  return f"export {validate_variable_name( name_ )}={shlex.quote( value_ )}"


def format_env_line(
  name_ : str ,
  value_ : str ,
) -> str:
  """Return `name="value"` with the escapes that dotenv readers expect."""

  escaped : str = (
    value_.replace( "\\", "\\\\" )
    .replace( '"', '\\"' )
    .replace( "$", "\\$" )
    .replace( "\n", "\\n" )
  )

  return f'{validate_variable_name( name_ )}="{escaped}"'


def write_env_variable(
  directory_ : Path ,
  name_ : str ,
  value_ : str ,
) -> Path:
  """
  Set a variable in `directory_/.env` with owner only permissions.

  An existing line of the same variable is replaced. Other lines stay.

  Args:
    directory_ (Path): Folder that holds the `.env` file.
    name_ (str): Variable name.
    value_ (str): Decrypted secret.

  Returns:
    Path: The `.env` file.

  Raises:
    Export_Error: If the name is invalid or the file cannot be written.
  """

  line : str = format_env_line( name_, value_ )
  name : str = validate_variable_name( name_ )
  target : Path = directory_ / ENV_FILE_NAME

  try:
    existing : list[str] = (
      target.read_text().splitlines() if target.is_file() else []
    )
    kept : list[str] = [
      row
      for row in existing
      if not row.lstrip().startswith( ( f"{name}=", f"export {name}=" ) )
    ]
    file_descriptor : int = os.open(
      target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
    )
    with os.fdopen( file_descriptor, "w" ) as handle:
      handle.write( "\n".join( kept + [ line ] ) + "\n" )
    os.chmod( target, 0o600 )
  except OSError as error:
    raise Export_Error( f"cannot write {target}: {error}" ) from error

  assert target.is_file(), ".env file missing after export"

  return target
