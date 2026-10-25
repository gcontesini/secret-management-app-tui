"""Tests for configuration helpers."""

from pathlib import Path

from keyvault.config import (
  DEFAULT_PALETTE,
  load_last_folder,
  load_palette,
  save_last_folder,
)


def test_default_palette_without_file( tmp_path : Path ) -> None:
  assert load_palette( tmp_path / "none.toml" ) == DEFAULT_PALETTE


def test_palette_override_and_validation( tmp_path : Path ) -> None:
  file : Path = tmp_path / "p.toml"
  file.write_text( 'green = "#00ff00"\nred = "nothex"\nbogus = "#000000"\n' )

  palette = load_palette( file )

  assert palette[ "green" ] == "#00ff00"
  assert palette[ "red" ] == DEFAULT_PALETTE[ "red" ]
  assert "bogus" not in palette


def test_broken_toml_falls_back( tmp_path : Path ) -> None:
  file : Path = tmp_path / "p.toml"
  file.write_text( "= = =" )

  assert load_palette( file ) == DEFAULT_PALETTE


def test_last_folder_round_trip( tmp_path : Path ) -> None:
  assert load_last_folder() is None
  save_last_folder( tmp_path )

  assert load_last_folder() == tmp_path


def test_last_folder_ignored_when_deleted( tmp_path : Path ) -> None:
  gone : Path = tmp_path / "gone"
  gone.mkdir()
  save_last_folder( gone )
  gone.rmdir()

  assert load_last_folder() is None
