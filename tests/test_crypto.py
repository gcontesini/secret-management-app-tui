"""Tests for the ccrypt wrapper."""

import pytest

from keyvault import crypto
from keyvault.crypto import (
  Crypto_Error,
  Wrong_Password_Error,
  decrypt_bytes,
  encrypt_bytes,
)


@pytest.mark.parametrize(
  "payload",
  [ b"x", b"line1\nline2\n", "ação 🔑".encode(), bytes( range( 256 ) ), b"" ],
)
def test_round_trip( payload : bytes ) -> None:
  assert decrypt_bytes( encrypt_bytes( payload, "pw" ), "pw" ) == payload


def test_ciphertext_hides_plaintext() -> None:
  assert b"topsecret" not in encrypt_bytes( b"topsecret", "pw" )


def test_wrong_password() -> None:
  with pytest.raises( Wrong_Password_Error ):
    decrypt_bytes( encrypt_bytes( b"a", "right" ), "wrong" )


def test_garbage_input() -> None:
  with pytest.raises( Crypto_Error ):
    decrypt_bytes( b"not ccrypt data", "pw" )


def test_empty_ciphertext() -> None:
  with pytest.raises( Crypto_Error ):
    decrypt_bytes( b"", "pw" )


def test_empty_password_is_rejected() -> None:
  with pytest.raises( AssertionError ):
    encrypt_bytes( b"a", "" )


def test_password_not_in_argv( monkeypatch : pytest.MonkeyPatch ) -> None:
  seen : list = []
  real_run = crypto.subprocess.run

  def spy( command , **kwargs ):
    seen.append( command )
    return real_run( command, **kwargs )

  monkeypatch.setattr( crypto.subprocess, "run", spy )
  encrypt_bytes( b"a", "s3cretpw" )

  assert all( "s3cretpw" not in part for part in seen[ 0 ] )


def test_missing_ccrypt( monkeypatch : pytest.MonkeyPatch ) -> None:
  monkeypatch.setattr( crypto.shutil, "which", lambda _: None )
  with pytest.raises( Crypto_Error ):
    crypto.find_ccrypt()


def test_bundled_ccrypt_is_preferred(
  monkeypatch : pytest.MonkeyPatch , tmp_path
) -> None:
  fake = tmp_path / "ccrypt"
  fake.write_text( "" )
  monkeypatch.setattr( crypto.sys, "_MEIPASS", str( tmp_path ), raising=False )

  assert crypto.find_ccrypt() == str( fake )
