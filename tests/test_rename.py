"""Tests for renaming files."""

from pathlib import Path

import pytest

from keyvault.app import Key_Vault_App
from keyvault.screens import Rename_Screen
from keyvault.vault import Vault, Vault_Error
from test_app import git_log


def test_rename_encrypted_keeps_hidden_and_suffix( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "bank", "pin", "pw" )

  assert vault.rename_entry( ".bank.cpt", "savings" ) == ".savings.cpt"
  assert vault.read_secret( ".savings.cpt", "pw" ) == b"pin"
  assert not ( secrets_dir / ".bank.cpt" ).exists()
  assert git_log( secrets_dir )[ 0 ] == "rename .bank.cpt to .savings.cpt"


def test_rename_encrypted_accepts_typed_suffix( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "a", "x", "pw" )

  assert vault.rename_entry( ".a.cpt", ".b.cpt" ) == ".b.cpt"


def test_rename_plaintext_untracked( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  ( secrets_dir / "note.txt" ).write_text( "x" )

  assert vault.rename_entry( "note.txt", "memo.txt" ) == "memo.txt"
  assert ( secrets_dir / "memo.txt" ).read_text() == "x"
  assert len( git_log( secrets_dir ) ) == 1


@pytest.mark.parametrize( "new", [ "", "a/b", "..", ".git", ".gitignore" ] )
def test_rename_rejects_bad_names( secrets_dir : Path , new : str ) -> None:
  vault : Vault = Vault( secrets_dir )
  ( secrets_dir / "f" ).write_text( "x" )

  with pytest.raises( Vault_Error ):
    vault.rename_entry( "f", new )


def test_rename_rejects_collision_same_name_and_missing(
  secrets_dir : Path
) -> None:
  vault : Vault = Vault( secrets_dir )
  ( secrets_dir / "f" ).write_text( "1" )
  ( secrets_dir / "g" ).write_text( "2" )

  with pytest.raises( Vault_Error, match="already exists" ):
    vault.rename_entry( "f", "g" )
  with pytest.raises( Vault_Error, match="equals" ):
    vault.rename_entry( "f", "f" )
  with pytest.raises( Vault_Error, match="does not exist" ):
    vault.rename_entry( "nope", "x" )
  assert ( secrets_dir / "g" ).read_text() == "2"


async def test_rename_dialog( secrets_dir : Path ) -> None:
  Vault( secrets_dir ).add_secret( "bank", "pin", "pw" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "f2" )
    await pilot.pause()
    assert isinstance( app.screen, Rename_Screen )
    app.screen.query_one( "#new-name" ).value = "savings"
    await pilot.press( "enter" )
    await pilot.pause()
    assert app.cursor_name() == ".savings.cpt"

  assert ( secrets_dir / ".savings.cpt" ).is_file()


async def test_rename_dialog_cancel_and_empty( secrets_dir : Path ) -> None:
  ( secrets_dir / "f" ).write_text( "x" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "f2" )
    await pilot.pause()
    app.screen.query_one( "#new-name" ).value = ""
    await pilot.press( "enter" )
    await pilot.pause()
    assert isinstance( app.screen, Rename_Screen )
    await pilot.press( "escape" )
    await pilot.pause()
    assert not isinstance( app.screen, Rename_Screen )

  assert ( secrets_dir / "f" ).is_file()


async def test_rename_dialog_collision_notifies( secrets_dir : Path ) -> None:
  ( secrets_dir / "f" ).write_text( "1" )
  ( secrets_dir / "g" ).write_text( "2" )
  app : Key_Vault_App = Key_Vault_App( folder_=secrets_dir )

  async with app.run_test() as pilot:
    await pilot.pause()
    await pilot.press( "f2" )
    await pilot.pause()
    app.screen.query_one( "#new-name" ).value = "g"
    await pilot.press( "enter" )
    await pilot.pause()
    assert any( "already exists" in n.message for n in app._notifications )
