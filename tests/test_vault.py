"""Tests for the vault operations."""

import subprocess
from pathlib import Path

import pytest

from keyvault.crypto import Wrong_Password_Error
from keyvault.vault import Vault, Vault_Error, validate_entry_name


def git_log( folder : Path ) -> list[str]:
  return subprocess.run(
    [ "git", "-C", str( folder ), "log", "--format=%s" ],
    capture_output=True, text=True, check=True,
  ).stdout.split( "\n" )[ :-1 ]


def test_add_secret_commits_with_file_name( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )

  name : str = vault.add_secret( "bank", "pin 1234", "pw" )

  assert name == ".bank.cpt"
  assert git_log( secrets_dir )[ 0 ] == ".bank.cpt"
  assert b"1234" not in ( secrets_dir / name ).read_bytes()
  assert vault.read_secret( name, "pw" ) == b"pin 1234"


def test_add_secret_refuses_overwrite( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "a", "1", "pw" )

  with pytest.raises( Vault_Error ):
    vault.add_secret( ".a.cpt", "2", "pw" )


def test_add_secret_refuses_plaintext_twin( secrets_dir : Path ) -> None:
  ( secrets_dir / ".a" ).write_text( "plain" )

  with pytest.raises( Vault_Error ):
    Vault( secrets_dir ).add_secret( "a", "1", "pw" )


@pytest.mark.parametrize(
  "bad", [ "", "  ", ".", "..", "../x", "a/b", ".git", ".gitignore", "a\\b" ]
)
def test_invalid_names( bad : str ) -> None:
  with pytest.raises( Vault_Error ):
    validate_entry_name( bad )


def test_list_entries_states( secrets_dir : Path ) -> None:
  ( secrets_dir / "plain.txt" ).write_text( "x" )
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "enc", "x", "pw" )
  ( secrets_dir / "sub" ).mkdir()

  states : dict[str, bool] = {
    e.name: e.encrypted for e in vault.list_entries()
  }

  assert states == { ".enc.cpt": True, "plain.txt": False }


def test_encrypt_entry_removes_plaintext( secrets_dir : Path ) -> None:
  ( secrets_dir / "note.txt" ).write_text( "hello" )
  vault : Vault = Vault( secrets_dir )

  name : str = vault.encrypt_entry( "note.txt", "pw" )

  assert name == ".note.txt.cpt"
  assert not ( secrets_dir / "note.txt" ).exists()
  assert git_log( secrets_dir )[ 0 ] == ".note.txt.cpt"
  assert vault.read_secret( name, "pw" ) == b"hello"


def test_encrypt_entry_rejects_encrypted( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "a", "1", "pw" )

  with pytest.raises( Vault_Error ):
    vault.encrypt_entry( ".a.cpt", "pw" )


def test_decrypt_entry_round_trip_and_history( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "a", "v1", "pw" )

  plain : str = vault.decrypt_entry( ".a.cpt", "pw" )
  ( secrets_dir / plain ).write_text( "v2" )
  vault.encrypt_entry( plain, "pw" )

  assert plain == ".a"
  assert len( vault.history( ".a.cpt" ) ) == 2
  assert vault.read_secret( ".a.cpt", "pw" ) == b"v2"


def test_decrypt_wrong_password_keeps_file( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "a", "v1", "pw" )

  with pytest.raises( Wrong_Password_Error ):
    vault.decrypt_entry( ".a.cpt", "nope" )

  assert ( secrets_dir / ".a.cpt" ).is_file()
  assert not ( secrets_dir / ".a" ).exists()


def test_decrypt_plaintext_rejected( secrets_dir : Path ) -> None:
  ( secrets_dir / "a" ).write_text( "x" )

  with pytest.raises( Vault_Error ):
    Vault( secrets_dir ).decrypt_entry( "a", "pw" )


def test_delete_requires_exact_name( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "a", "1", "pw" )

  for wrong in ( "", "a", ".A.cpt", ".a.cpt " ):
    with pytest.raises( Vault_Error ):
      vault.delete_entry( ".a.cpt", wrong )
    assert ( secrets_dir / ".a.cpt" ).exists()

  vault.delete_entry( ".a.cpt", ".a.cpt" )

  assert not ( secrets_dir / ".a.cpt" ).exists()
  assert git_log( secrets_dir )[ 0 ] == "delete .a.cpt"


def test_delete_untracked_plaintext( secrets_dir : Path ) -> None:
  ( secrets_dir / "p.txt" ).write_text( "x" )
  vault : Vault = Vault( secrets_dir )

  vault.delete_entry( "p.txt", "p.txt" )

  assert not ( secrets_dir / "p.txt" ).exists()


def test_delete_missing_file( secrets_dir : Path ) -> None:
  with pytest.raises( Vault_Error ):
    Vault( secrets_dir ).delete_entry( "ghost", "ghost" )


def test_read_old_revision( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "a", "v1", "pw" )
  plain : str = vault.decrypt_entry( ".a.cpt", "pw" )
  ( secrets_dir / plain ).write_text( "v2" )
  vault.encrypt_entry( plain, "pw" )

  oldest = vault.history( "a" )[ -1 ]

  assert vault.read_revision( "a", oldest.commit, "pw" ) == b"v1"


def test_symlink_escape_is_rejected( secrets_dir : Path , tmp_path : Path ) -> None:
  outside : Path = tmp_path / "outside.txt"
  outside.write_text( "x" )
  ( secrets_dir / "link" ).symlink_to( outside )

  with pytest.raises( Vault_Error ):
    Vault( secrets_dir ).read_secret( "link", "pw" )


@pytest.mark.parametrize(
  "raw, expected",
  [ ( "a", ".a" ), ( ".a", ".a" ), ( "..a", ".a" ), ( "x.txt", ".x.txt" ) ],
)
def test_hidden_name( raw : str , expected : str ) -> None:
  from keyvault.vault import hidden_name

  assert hidden_name( raw ) == expected


def test_new_secrets_are_hidden_and_listed( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "bank", "1", "pw" )
  vault.add_secret( ".card", "2", "pw" )

  visible : list[str] = [
    p.name for p in secrets_dir.iterdir() if not p.name.startswith( "." )
  ]
  names : list[str] = [ e.name for e in vault.list_entries() ]

  assert visible == []
  assert names == [ ".bank.cpt", ".card.cpt" ]
  assert ".gitignore" not in names


def test_hidden_plaintext_is_listed_as_unencrypted( secrets_dir : Path ) -> None:
  ( secrets_dir / ".raw" ).write_text( "x" )

  entries = Vault( secrets_dir ).list_entries()

  assert [ ( e.name, e.encrypted ) for e in entries ] == [ ( ".raw", False ) ]


def test_encrypt_hides_visible_plaintext( secrets_dir : Path ) -> None:
  ( secrets_dir / "visible.txt" ).write_text( "x" )
  vault : Vault = Vault( secrets_dir )

  assert vault.encrypt_entry( "visible.txt", "pw" ) == ".visible.txt.cpt"
  assert vault.history( "visible.txt" )[ 0 ].message == ".visible.txt.cpt"


def test_octal_mode_and_chmod( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  ( secrets_dir / "f" ).write_text( "x" )

  vault.set_permissions( "f", "640" )

  assert vault.octal_mode( "f" ) == "640"
  assert vault.list_entries()[ 0 ].mode == "-rw-r-----"


@pytest.mark.parametrize( "mode", [ "9", "abc", "12345", "-1" ] )
def test_chmod_rejects_bad_mode( secrets_dir : Path , mode : str ) -> None:
  vault : Vault = Vault( secrets_dir )
  ( secrets_dir / "f" ).write_text( "x" )

  with pytest.raises( Vault_Error ):
    vault.set_permissions( "f", mode )


def test_chown_current_group_and_unknown_group( secrets_dir : Path ) -> None:
  import grp
  import os

  vault : Vault = Vault( secrets_dir )
  ( secrets_dir / "f" ).write_text( "x" )
  own_group : str = grp.getgrgid( os.getgid() ).gr_name

  vault.set_permissions( "f", None, "", own_group )

  with pytest.raises( Vault_Error ):
    vault.set_permissions( "f", None, "", "no_such_group_keyvault" )


def test_chown_other_owner_refused_for_non_root( secrets_dir : Path ) -> None:
  import os

  if os.geteuid() == 0:
    pytest.skip( "root may change the owner" )

  vault : Vault = Vault( secrets_dir )
  ( secrets_dir / "f" ).write_text( "x" )

  with pytest.raises( Vault_Error ):
    vault.set_permissions( "f", None, "root" )


def test_set_permissions_missing_file( secrets_dir : Path ) -> None:
  with pytest.raises( Vault_Error ):
    Vault( secrets_dir ).set_permissions( "nope", "600" )


def test_unknown_backend_rejected( secrets_dir : Path ) -> None:
  with pytest.raises( Vault_Error ):
    Vault( secrets_dir, "gpg" )
