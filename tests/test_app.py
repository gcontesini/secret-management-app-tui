"""Pilot driven tests of the Textual application."""

import subprocess
from pathlib import Path

from textual.widgets import Button, DataTable, Input, RichLog, TextArea

from keyvault.app import Key_Vault_App, build_theme
from keyvault.config import DEFAULT_PALETTE
from keyvault.screens import (
  Add_Secret_Screen,
  Folder_Screen,
  History_Screen,
  Password_Screen,
)
from keyvault.vault import Vault


def panel_text( app : Key_Vault_App ) -> str:
  panel : RichLog = app.query_one( "#secret-panel", RichLog )

  return "\n".join(
    "".join( segment.text for segment in strip ) for strip in panel.lines
  )


async def type_text( pilot , text : str ) -> None:
  for character in text:
    await pilot.press( character )


async def give_password( pilot , password : str , confirm : bool = False ) -> None:
  await pilot.pause()
  await type_text( pilot, password )
  if confirm:
    await pilot.press( "tab" )
    await type_text( pilot, password )
  await pilot.press( "enter" )
  await pilot.pause()


def git_log( folder : Path ) -> list[str]:
  return subprocess.run(
    [ "git", "-C", str( folder ), "log", "--format=%s" ],
    capture_output=True, text=True, check=True,
  ).stdout.splitlines()


async def test_lists_files_with_state_colors( secrets_dir : Path ) -> None:
  ( secrets_dir / "plain.txt" ).write_text( "x" )
  Vault( secrets_dir ).add_secret( "enc", "x", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    table : DataTable = app.query_one( "#entries", DataTable )
    styles : dict[str, str] = {
      key: str( table.get_row( key )[ 1 ].style )
      for key in ( ".enc.cpt", "plain.txt" )
    }

  assert styles[ ".enc.cpt" ] == DEFAULT_PALETTE[ "green" ]
  assert styles[ "plain.txt" ] == DEFAULT_PALETTE[ "red" ]


async def test_view_multiple_files_asks_password_once( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "one", "alpha-secret", "pw" )
  vault.add_secret( "two", "beta-secret", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "a", "v" )
    await give_password( pilot, "pw" )
    assert not isinstance( app.screen, Password_Screen )
    text : str = panel_text( app )
    assert "alpha-secret" in text and "beta-secret" in text

    await pilot.press( "v" )
    await pilot.pause()
    assert not isinstance( app.screen, Password_Screen )


async def test_wrong_password_clears_cache( secrets_dir : Path ) -> None:
  Vault( secrets_dir ).add_secret( "one", "alpha-secret", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "v" )
    await give_password( pilot, "bad" )
    assert app.password is None
    assert "alpha-secret" not in panel_text( app )


async def test_delete_needs_exact_name( secrets_dir : Path ) -> None:
  Vault( secrets_dir ).add_secret( "one", "x", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "x" )
    await pilot.pause()
    await type_text( pilot, ".one.cp" )
    assert app.screen.query_one( "#delete", Button ).disabled is True
    await pilot.press( "enter" )
    await pilot.pause()
    assert ( secrets_dir / ".one.cpt" ).exists()

    await pilot.press( "t" )
    assert app.screen.query_one( "#delete", Button ).disabled is False
    await pilot.press( "enter" )
    await pilot.pause()

  assert not ( secrets_dir / ".one.cpt" ).exists()


async def test_new_secret_is_encrypted_and_committed( secrets_dir : Path ) -> None:
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "n" )
    await pilot.pause()
    await type_text( pilot, "wifi" )
    app.screen.query_one( "#secret", TextArea ).text = "hunter2"
    await pilot.press( "ctrl+s" )
    await give_password( pilot, "pw", confirm=True )

  assert ( secrets_dir / ".wifi.cpt" ).is_file()
  assert git_log( secrets_dir )[ 0 ] == ".wifi.cpt"
  assert Vault( secrets_dir ).read_secret( ".wifi.cpt", "pw" ) == b"hunter2"


async def test_encrypt_marked_plaintext( secrets_dir : Path ) -> None:
  ( secrets_dir / "a.txt" ).write_text( "aa" )
  ( secrets_dir / "b.txt" ).write_text( "bb" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "a", "e" )
    await give_password( pilot, "pw", confirm=True )

  assert sorted( p.name for p in secrets_dir.glob( "*.cpt" ) ) == [
    ".a.txt.cpt", ".b.txt.cpt",
  ]
  assert not ( secrets_dir / "a.txt" ).exists()


async def test_decrypt_to_disk( secrets_dir : Path ) -> None:
  Vault( secrets_dir ).add_secret( "one", "alpha", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "d" )
    await give_password( pilot, "pw" )

  assert ( secrets_dir / ".one" ).read_text() == "alpha"
  assert not ( secrets_dir / ".one.cpt" ).exists()


async def test_history_shows_old_version( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "one", "first-version", "pw" )
  plain : str = vault.decrypt_entry( ".one.cpt", "pw" )
  ( secrets_dir / plain ).write_text( "second-version" )
  vault.encrypt_entry( plain, "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "h" )
    await pilot.pause()
    await pilot.pause()
    assert isinstance( app.screen, History_Screen )
    await pilot.press( "down", "enter" )
    await give_password( pilot, "pw" )
    assert "first-version" in panel_text( app )


async def test_lock_forgets_password_and_clears_panel( secrets_dir : Path ) -> None:
  Vault( secrets_dir ).add_secret( "one", "alpha", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "v" )
    await give_password( pilot, "pw" )
    assert "alpha" in panel_text( app )
    await pilot.press( "l" )
    await pilot.pause()
    assert app.password is None
    assert panel_text( app ) == ""


async def test_folder_picker_opens_when_no_folder( secrets_dir : Path ) -> None:
  app : Key_Vault_App = Key_Vault_App( folder_=None )

  async with app.run_test() as pilot:
    await pilot.pause()
    app.screen.query_one( "#path", Input ).value = str( secrets_dir )
    await pilot.press( "enter" )
    await pilot.pause()
    assert app.vault is not None and app.vault.root == secrets_dir.resolve()


async def test_mark_toggle_and_mark_all( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "one", "1", "pw" )
  vault.add_secret( "two", "2", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "space" )
    assert app.marked == { ".one.cpt" }
    await pilot.press( "space" )
    assert app.marked == set()
    await pilot.press( "a" )
    assert app.marked == { ".one.cpt", ".two.cpt" }
    await pilot.press( "a" )
    assert app.marked == set()


async def test_password_dialog_validation( secrets_dir : Path ) -> None:
  ( secrets_dir / "a.txt" ).write_text( "aa" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "e" )
    await pilot.pause()
    await pilot.press( "enter" )
    assert isinstance( app.screen, Password_Screen )
    await type_text( pilot, "abc" )
    await pilot.press( "tab" )
    await type_text( pilot, "abd" )
    await pilot.press( "enter" )
    assert isinstance( app.screen, Password_Screen )
    await pilot.press( "escape" )
    await pilot.pause()

  assert ( secrets_dir / "a.txt" ).exists()
  assert app.password is None


async def test_cancelled_dialogs_change_nothing( secrets_dir : Path ) -> None:
  Vault( secrets_dir ).add_secret( "one", "1", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    for key in ( "x", "n", "h", "o" ):
      await pilot.press( key )
      await pilot.pause()
      await pilot.pause()
      await pilot.press( "escape" )
      await pilot.pause()
    await pilot.press( "d" )
    await pilot.pause()
    await pilot.press( "escape" )
    await pilot.pause()

  assert ( secrets_dir / ".one.cpt" ).exists()


async def test_new_secret_validation_and_collision( secrets_dir : Path ) -> None:
  Vault( secrets_dir ).add_secret( "dup", "1", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "n" )
    await pilot.pause()
    await pilot.press( "ctrl+s" )
    assert isinstance( app.screen, Add_Secret_Screen )
    await type_text( pilot, "dup" )
    await pilot.press( "ctrl+s" )
    assert isinstance( app.screen, Add_Secret_Screen )
    app.screen.query_one( "#secret", TextArea ).text = "2"
    await pilot.press( "ctrl+s" )
    await give_password( pilot, "pw", confirm=True )

  assert Vault( secrets_dir ).read_secret( ".dup.cpt", "pw" ) == b"1"


async def test_empty_state_actions_do_nothing( secrets_dir : Path ) -> None:
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    for key in ( "space", "v", "e", "d", "x", "h", "r", "a" ):
      await pilot.press( key )
      await pilot.pause()
    assert not isinstance( app.screen, Password_Screen )


async def test_view_plaintext_needs_no_password( secrets_dir : Path ) -> None:
  ( secrets_dir / "p.txt" ).write_text( "open-text" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "v" )
    await pilot.pause()
    assert "open-text" in panel_text( app )


async def test_folder_picker_rejects_missing_path( secrets_dir : Path ) -> None:
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "o" )
    await pilot.pause()
    app.screen.query_one( "#path", Input ).value = str( secrets_dir / "nope" )
    await pilot.press( "enter" )
    await pilot.pause()
    assert isinstance( app.screen, Folder_Screen )


async def test_decrypt_wrong_password_keeps_files( secrets_dir : Path ) -> None:
  Vault( secrets_dir ).add_secret( "one", "1", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "d" )
    await give_password( pilot, "bad" )

  assert ( secrets_dir / ".one.cpt" ).exists()
  assert app.password is None


async def test_unopenable_folder_is_reported( tmp_path : Path ) -> None:
  app : Key_Vault_App = Key_Vault_App( folder_=tmp_path / "missing" )

  async with app.run_test() as pilot:
    await pilot.pause()

  assert app.vault is None


def test_build_theme_uses_palette() -> None:
  theme = build_theme( DEFAULT_PALETTE )

  assert theme.success == DEFAULT_PALETTE[ "green" ]
  assert theme.error == DEFAULT_PALETTE[ "red" ]


def test_menu_text_starts_with_label_and_lists_commands() -> None:
  from keyvault.app import MENU_ITEMS, MENU_LABEL, build_menu

  text : str = build_menu( DEFAULT_PALETTE ).plain

  assert text.startswith( f" {MENU_LABEL} " )
  assert all( label in text for _, label in MENU_ITEMS )


async def test_menu_bar_is_below_header_and_lists_hidden_files(
  secrets_dir : Path ,
) -> None:
  Vault( secrets_dir ).add_secret( "hid", "x", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    menubar = app.query_one( "#menubar" )
    table : DataTable = app.query_one( "#entries", DataTable )

    assert menubar.region.y < table.region.y
    assert menubar.region.y <= 1
    assert table.row_count == 1
    assert ".hid.cpt" in [ r.value for r in table.rows ]
