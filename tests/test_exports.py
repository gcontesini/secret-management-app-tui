"""Tests for the .env and export formatters."""

import stat
import subprocess
from pathlib import Path

import pytest

from keyvault.exports import (
  Export_Error,
  format_env_line,
  format_export_line,
  validate_variable_name,
  write_env_variable,
)

TRICKY : str = "a b'c\"d$e`f\\g"


@pytest.mark.parametrize( "name", [ "A", "_x", "api_key_2" ] )
def test_valid_names( name : str ) -> None:
  assert validate_variable_name( f" {name} " ) == name


@pytest.mark.parametrize( "name", [ "", "1a", "a-b", "a b", "a=b", "$x" ] )
def test_invalid_names( name : str ) -> None:
  with pytest.raises( Export_Error ):
    validate_variable_name( name )


def test_export_line_survives_bash() -> None:
  line : str = format_export_line( "MY_SECRET", TRICKY )
  result : subprocess.CompletedProcess = subprocess.run(
    [ "bash", "-c", f'{line}; printf %s "$MY_SECRET"' ],
    capture_output=True, text=True, check=True,
  )

  assert result.stdout == TRICKY


def test_env_line_escapes() -> None:
  assert format_env_line( "K", 'a"b$c\nd\\' ) == 'K="a\\"b\\$c\\nd\\\\"'


def test_write_env_creates_private_file( tmp_path : Path ) -> None:
  target : Path = write_env_variable( tmp_path, "TOKEN", "abc" )

  assert target == tmp_path / ".env"
  assert target.read_text() == 'TOKEN="abc"\n'
  assert stat.S_IMODE( target.stat().st_mode ) == 0o600


def test_write_env_replaces_same_variable( tmp_path : Path ) -> None:
  ( tmp_path / ".env" ).write_text( 'A="1"\nTOKEN="old"\nexport TOKEN=zz\n' )

  write_env_variable( tmp_path, "TOKEN", "new" )

  assert ( tmp_path / ".env" ).read_text() == 'A="1"\nTOKEN="new"\n'


def test_write_env_reports_unwritable( tmp_path : Path ) -> None:
  with pytest.raises( Export_Error ):
    write_env_variable( tmp_path / "missing", "A", "b" )
