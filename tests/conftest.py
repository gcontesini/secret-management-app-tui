"""Shared fixtures."""

from pathlib import Path

import pytest


@pytest.fixture( autouse=True )
def isolated_config(
  tmp_path_factory : pytest.TempPathFactory ,
  monkeypatch : pytest.MonkeyPatch ,
) -> Path:
  """Point XDG_CONFIG_HOME to a temp dir so tests never touch real config."""

  config_home : Path = tmp_path_factory.mktemp( "xdg" )
  monkeypatch.setenv( "XDG_CONFIG_HOME", str( config_home ) )

  return config_home


@pytest.fixture
def secrets_dir( tmp_path : Path ) -> Path:
  """Empty folder that stands for a user secrets folder."""

  folder : Path = tmp_path / "secrets"
  folder.mkdir()

  return folder
