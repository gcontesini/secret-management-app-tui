"""Clipboard helper tests with stand-in command line tools."""

import os
from pathlib import Path

import pytest

from keyvault import clipboard


@pytest.fixture
def fake_tools( tmp_path : Path , monkeypatch : pytest.MonkeyPatch ) -> Path:
  bin_dir : Path = tmp_path / "bin"
  bin_dir.mkdir()
  store : Path = tmp_path / "store"
  for name, body in {
    "wl-copy": f'cat > "{store}"',
    "wl-paste": f'cat "{store}"',
  }.items():
    script : Path = bin_dir / name
    script.write_text( f"#!/bin/sh\n{body}\n" )
    script.chmod( 0o755 )
  monkeypatch.setenv( "PATH", f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin" )

  return store


def test_copy_then_read( fake_tools : Path ) -> None:
  assert clipboard.copy_text( "multi\nline ünï" ) is True
  assert clipboard.read_text() == "multi\nline ünï"


def test_no_tools( monkeypatch : pytest.MonkeyPatch , tmp_path : Path ) -> None:
  monkeypatch.setenv( "PATH", str( tmp_path ) )

  assert clipboard.copy_text( "x" ) is False
  assert clipboard.read_text() is None


def test_failing_tool_falls_through( tmp_path : Path , monkeypatch : pytest.MonkeyPatch ) -> None:
  bin_dir : Path = tmp_path / "bin"
  bin_dir.mkdir()
  for name in ( "wl-copy", "wl-paste" ):
    ( bin_dir / name ).write_text( "#!/bin/sh\nexit 1\n" )
    ( bin_dir / name ).chmod( 0o755 )
  monkeypatch.setenv( "PATH", str( bin_dir ) )

  assert clipboard.copy_text( "x" ) is False
  assert clipboard.read_text() is None
  assert os.path.isdir( bin_dir )
