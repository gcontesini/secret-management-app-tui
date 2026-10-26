"""Pilot tests for menu text and clipboard and backend and permissions and export."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from textual.widgets import Footer, Input, RadioSet, Static

from keyvault import clipboard
from keyvault.app import QUIT_DESCRIPTION, Key_Vault_App
from keyvault.screens import (
  Add_Secret_Screen,
  Export_Screen,
  Password_Screen,
  Permissions_Screen,
)
from keyvault.vault import Vault
from test_app import give_password, panel_text, type_text


@pytest.fixture
def system_clipboard( monkeypatch : pytest.MonkeyPatch ) -> dict[str, str]:
  box : dict[str, str] = { "text": "" }
  monkeypatch.setattr(
    clipboard, "copy_text", lambda text_: box.update( text=text_ ) or True
  )
  monkeypatch.setattr( clipboard, "read_text", lambda: box[ "text" ] )

  return box


async def test_footer_and_menu_hide_palette( secrets_dir : Path ) -> None:
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    assert app.query_one( Footer ).show_command_palette is False
    menu : str = app.query_one( "#menubar", Static ).render().plain

  assert "Palette" not in menu
  assert "m Permissions" in menu and "t Export" in menu and "b Backend" in menu


async def test_quit_command_text( secrets_dir : Path ) -> None:
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    quit_commands : list = [
      c for c in app.get_system_commands( app.screen ) if c.title == "Quit"
    ]

  assert [ c.help for c in quit_commands ] == [ QUIT_DESCRIPTION ]
  assert QUIT_DESCRIPTION == "Quit the application"


async def test_ctrl_c_copies_panel_and_ctrl_v_opens_new_secret(
  secrets_dir : Path , system_clipboard : dict[str, str]
) -> None:
  Vault( secrets_dir ).add_secret( "one", "alpha-secret", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "ctrl+c" )
    assert system_clipboard[ "text" ] == ""

    await pilot.press( "v" )
    await give_password( pilot, "pw" )
    await pilot.press( "ctrl+c" )
    assert "alpha-secret" in system_clipboard[ "text" ]

    system_clipboard[ "text" ] = "pasted-value"
    await pilot.press( "ctrl+v" )
    await pilot.pause()
    assert isinstance( app.screen, Add_Secret_Screen )
    assert app.screen.query_one( "#secret" ).text == "pasted-value"


async def test_ctrl_v_with_empty_clipboard_does_nothing(
  secrets_dir : Path , system_clipboard : dict[str, str]
) -> None:
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "ctrl+v" )
    await pilot.pause()
    assert not isinstance( app.screen, Add_Secret_Screen )


async def test_ctrl_v_pastes_into_input( secrets_dir : Path , system_clipboard : dict[str, str] ) -> None:
  system_clipboard[ "text" ] = "from-clipboard"
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "n" )
    await pilot.pause()
    await pilot.press( "ctrl+v" )
    assert app.screen.query_one( "#name", Input ).value == "from-clipboard"


async def test_permissions_dialog_changes_mode( secrets_dir : Path ) -> None:
  ( secrets_dir / "f.txt" ).write_text( "x" )
  ( secrets_dir / "f.txt" ).chmod( 0o644 )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "m" )
    await pilot.pause()
    assert isinstance( app.screen, Permissions_Screen )
    mode_input : Input = app.screen.query_one( "#mode", Input )
    assert mode_input.value == "644"
    mode_input.value = "600"
    await pilot.press( "enter" )
    await pilot.pause()

  assert stat.S_IMODE( ( secrets_dir / "f.txt" ).stat().st_mode ) == 0o600


async def test_permissions_dialog_requires_a_change( secrets_dir : Path ) -> None:
  ( secrets_dir / "f.txt" ).write_text( "x" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "m" )
    await pilot.pause()
    app.screen.query_one( "#mode", Input ).value = ""
    await pilot.press( "enter" )
    await pilot.pause()
    assert isinstance( app.screen, Permissions_Screen )
    await pilot.press( "escape" )
    await pilot.pause()
    assert not isinstance( app.screen, Permissions_Screen )


async def test_permissions_dialog_reports_refused_owner( secrets_dir : Path ) -> None:
  if os.geteuid() == 0:
    pytest.skip( "root may change the owner" )
  ( secrets_dir / "f.txt" ).write_text( "x" )
  before : int = ( secrets_dir / "f.txt" ).stat().st_uid
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "m" )
    await pilot.pause()
    app.screen.query_one( "#owner", Input ).value = "root"
    await pilot.press( "enter" )
    await pilot.pause()
    messages : list[str] = [ n.message for n in app._notifications ]

  assert any( "cannot change" in m for m in messages )
  assert ( secrets_dir / "f.txt" ).stat().st_uid == before


async def test_export_to_env_file( secrets_dir : Path , tmp_path : Path , monkeypatch : pytest.MonkeyPatch ) -> None:
  work : Path = tmp_path / "work"
  work.mkdir()
  monkeypatch.chdir( work )
  Vault( secrets_dir ).add_secret( "tok", "value with $pecial", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "t" )
    await pilot.pause()
    assert isinstance( app.screen, Export_Screen )
    await type_text( pilot, "API_TOKEN" )
    await pilot.press( "enter" )
    await give_password( pilot, "pw" )

  assert ( work / ".env" ).read_text() == 'API_TOKEN="value with \\$pecial"\n'
  assert stat.S_IMODE( ( work / ".env" ).stat().st_mode ) == 0o600


async def test_export_rejects_invalid_name( secrets_dir : Path ) -> None:
  Vault( secrets_dir ).add_secret( "tok", "v", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "t" )
    await pilot.pause()
    await type_text( pilot, "bad-name" )
    await pilot.press( "enter" )
    await pilot.pause()
    assert not isinstance( app.screen, Password_Screen )
    assert any( "not a valid name" in n.message for n in app._notifications )


async def test_export_command_goes_to_stdout_queue_when_captured(
  secrets_dir : Path , monkeypatch : pytest.MonkeyPatch
) -> None:
  Vault( secrets_dir ).add_secret( "tok", "it's", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  class Pipe_Stdout:
    def isatty( self ) -> bool:
      return False

  monkeypatch.setattr( "keyvault.app.sys.__stdout__", Pipe_Stdout() )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "t" )
    await pilot.pause()
    await type_text( pilot, "MY_SECRET" )
    app.screen.query_one( "#format", RadioSet ).query( "RadioButton" )[ 1 ].value = True
    await pilot.press( "enter" )
    await give_password( pilot, "pw" )

  assert app.pending_exports == [ "export MY_SECRET='it'\"'\"'s'" ]


async def test_export_command_copied_when_stdout_is_terminal(
  secrets_dir : Path ,
  system_clipboard : dict[str, str] ,
  monkeypatch : pytest.MonkeyPatch ,
) -> None:
  Vault( secrets_dir ).add_secret( "tok", "abc", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  class Tty_Stdout:
    def isatty( self ) -> bool:
      return True

  monkeypatch.setattr( "keyvault.app.sys.__stdout__", Tty_Stdout() )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "t" )
    await pilot.pause()
    await type_text( pilot, "K" )
    app.screen.query_one( "#format", RadioSet ).query( "RadioButton" )[ 1 ].value = True
    await pilot.press( "enter" )
    await give_password( pilot, "pw" )

  assert system_clipboard[ "text" ] == "export K=abc"
  assert app.pending_exports == []


async def test_switch_backend_refuses_without_rage(
  secrets_dir : Path , monkeypatch : pytest.MonkeyPatch
) -> None:
  monkeypatch.setattr( shutil, "which", lambda _name: None )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir, backend_="ccrypt" )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "b" )
    await pilot.pause()
    assert app.backend == "ccrypt"
    assert any( "rage was not found" in n.message for n in app._notifications )


async def test_switch_backend_creates_age_file_and_persists(
  secrets_dir : Path , tmp_path : Path , monkeypatch : pytest.MonkeyPatch
) -> None:
  bin_dir : Path = tmp_path / "bin"
  bin_dir.mkdir()
  shutil.copy( Path( __file__ ).parent / "fake_rage.py", bin_dir / "rage" )
  ( bin_dir / "rage" ).chmod( 0o755 )
  monkeypatch.setenv( "PATH", f"{bin_dir}{os.pathsep}{os.environ[ 'PATH' ]}" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir, backend_="ccrypt" )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "b" )
    await pilot.pause()
    assert app.backend == "rage"
    assert "[rage]" in app.sub_title

    await pilot.press( "n" )
    await pilot.pause()
    await type_text( pilot, "bank" )
    app.screen.query_one( "#secret" ).text = "pin 1234"
    await pilot.press( "ctrl+s" )
    await give_password( pilot, "pw", confirm=True )
    await pilot.pause()
    await pilot.press( "v" )
    await pilot.pause()
    assert "pin 1234" in panel_text( app )

  assert ( secrets_dir / ".bank.age" ).is_file()
  assert Key_Vault_App( folder_=secrets_dir ).backend == "rage"
  log : str = subprocess.run(
    [ "git", "-C", str( secrets_dir ), "log", "--format=%s" ],
    capture_output=True, text=True, check=True,
  ).stdout
  assert ".bank.age" in log
