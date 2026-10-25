"""Tests for the command line entry point."""

from pathlib import Path

import pytest

import keyvault
from keyvault import cli
from keyvault.crypto import Crypto_Error


def test_parse_arguments_defaults() -> None:
  assert cli.parse_arguments( [] ).folder is None


def test_parse_arguments_folder( tmp_path : Path ) -> None:
  assert cli.parse_arguments( [ str( tmp_path ) ] ).folder == tmp_path


def test_version_flag( capsys : pytest.CaptureFixture ) -> None:
  with pytest.raises( SystemExit ):
    cli.parse_arguments( [ "--version" ] )

  assert keyvault.__version__ in capsys.readouterr().out


def test_run_exits_without_ccrypt( monkeypatch : pytest.MonkeyPatch ) -> None:
  def missing() -> str:
    raise Crypto_Error( "ccrypt was not found" )

  monkeypatch.setattr( cli, "find_ccrypt", missing )

  with pytest.raises( SystemExit, match="ccrypt was not found" ):
    cli.run( [] )


def test_run_exits_for_bad_folder( tmp_path : Path ) -> None:
  with pytest.raises( SystemExit, match="not a folder" ):
    cli.run( [ str( tmp_path / "nope" ) ] )


@pytest.mark.parametrize( "use_argument", [ True, False ] )
def test_run_starts_app(
  use_argument : bool , tmp_path : Path , monkeypatch : pytest.MonkeyPatch
) -> None:
  started : list = []

  class Fake_App:
    def __init__( self , folder_ ) -> None:
      started.append( folder_ )

    def run( self ) -> None:
      started.append( "run" )

  monkeypatch.setattr( cli, "Key_Vault_App", Fake_App )
  monkeypatch.setattr( cli, "load_last_folder", lambda: tmp_path )
  cli.run( [ str( tmp_path ) ] if use_argument else [] )

  assert started == [ tmp_path, "run" ]


def test_package_main_delegates( monkeypatch : pytest.MonkeyPatch ) -> None:
  called : list = []
  monkeypatch.setattr( cli, "run", lambda: called.append( True ) )
  keyvault.main()

  assert called == [ True ]
