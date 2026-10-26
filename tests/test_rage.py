"""Rage backend tests against a stand-in executable that uses /dev/tty."""

import os
import shutil
import stat
from pathlib import Path

import pytest

from keyvault import crypto
from keyvault.crypto import (
  BACKEND_RAGE,
  Crypto_Error,
  Wrong_Password_Error,
  backend_for_name,
  decrypt_bytes,
  encrypt_bytes,
)
from keyvault.vault import Vault


@pytest.fixture
def fake_rage( tmp_path : Path , monkeypatch : pytest.MonkeyPatch ) -> Path:
  bin_dir : Path = tmp_path / "bin"
  bin_dir.mkdir()
  target : Path = bin_dir / "rage"
  shutil.copy( Path( __file__ ).parent / "fake_rage.py", target )
  target.chmod( target.stat().st_mode | stat.S_IEXEC )
  monkeypatch.setenv( "PATH", f"{bin_dir}{os.pathsep}{os.environ[ 'PATH' ]}" )

  return target


def test_find_rage_missing( monkeypatch : pytest.MonkeyPatch ) -> None:
  monkeypatch.setattr( crypto.shutil, "which", lambda _name: None )

  with pytest.raises( Crypto_Error, match="rage was not found" ):
    crypto.find_rage()


def test_round_trip( fake_rage : Path ) -> None:
  encrypted : bytes = encrypt_bytes( b"s3cret\nline", "pw", BACKEND_RAGE )

  assert b"s3cret" not in encrypted
  assert decrypt_bytes( encrypted, "pw", BACKEND_RAGE ) == b"s3cret\nline"


def test_wrong_password( fake_rage : Path ) -> None:
  encrypted : bytes = encrypt_bytes( b"x", "pw", BACKEND_RAGE )

  with pytest.raises( Wrong_Password_Error ):
    decrypt_bytes( encrypted, "other", BACKEND_RAGE )


def test_backend_for_name() -> None:
  assert backend_for_name( ".a.cpt" ) == "ccrypt"
  assert backend_for_name( ".a.age" ) == "rage"
  with pytest.raises( Crypto_Error ):
    backend_for_name( "a.txt" )


def test_vault_mixes_backends( fake_rage : Path , secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  vault.add_secret( "old", "ccrypt-value", "pw" )
  vault.backend = BACKEND_RAGE
  created : str = vault.add_secret( "new", "rage-value", "pw" )

  assert created == ".new.age"
  assert vault.read_secret( ".old.cpt", "pw" ) == b"ccrypt-value"
  assert vault.read_secret( ".new.age", "pw" ) == b"rage-value"
  assert [ e.encrypted for e in vault.list_entries() ] == [ True, True ]
  assert len( vault.history( ".new.age" ) ) == 1
  commit : str = vault.history( ".new.age" )[ 0 ].commit
  assert vault.read_revision( ".new.age", commit, "pw" ) == b"rage-value"


def test_encrypt_decrypt_entry_with_rage(
  fake_rage : Path , secrets_dir : Path
) -> None:
  vault : Vault = Vault( secrets_dir, BACKEND_RAGE )
  ( secrets_dir / "plain.txt" ).write_text( "hello" )

  assert vault.encrypt_entry( "plain.txt", "pw" ) == ".plain.txt.age"
  assert vault.decrypt_entry( ".plain.txt.age", "pw" ) == ".plain.txt"
  assert ( secrets_dir / ".plain.txt" ).read_text() == "hello"


def test_old_gitignore_gets_age_rule( secrets_dir : Path ) -> None:
  vault : Vault = Vault( secrets_dir )
  ( secrets_dir / ".gitignore" ).write_text( "*\n!.gitignore\n!*.cpt\n" )
  vault.git.commit_paths( [ ".gitignore" ], "old rules" )

  Vault( secrets_dir )

  assert "!*.age" in ( secrets_dir / ".gitignore" ).read_text().splitlines()
