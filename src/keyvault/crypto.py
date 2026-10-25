"""Thin wrapper around the ccrypt command line tool.

The password travels to ccrypt through an environment variable that only
exists in the child process. It never appears on the command line and
plaintext never touches the disk.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

CCRYPT_KEY_ENV : str = "KEYVAULT_CCRYPT_KEY"
CCRYPT_SUFFIX : str = ".cpt"
CCRYPT_TIMEOUT_SECONDS : float = 30.0


class Crypto_Error( Exception ):
  """Raised when ccrypt is missing or fails."""


class Wrong_Password_Error( Crypto_Error ):
  """Raised when ccrypt rejects the supplied password."""


def find_ccrypt() -> str:
  """
  Locate the ccrypt executable.

  A binary bundled by PyInstaller takes priority over the system PATH.

  Returns:
    str: Absolute path to ccrypt.

  Raises:
    Crypto_Error: If ccrypt cannot be found.
  """

  executable_name : str = "ccrypt.exe" if os.name == "nt" else "ccrypt"
  bundle_dir : Optional[str] = getattr( sys, "_MEIPASS", None )

  if bundle_dir is not None:
    bundled : Path = Path( bundle_dir ) / executable_name
    if bundled.is_file():
      return str( bundled )

  found : Optional[str] = shutil.which( "ccrypt" )

  if found is None:
    raise Crypto_Error(
      "ccrypt was not found. Run `just install-system-deps` first."
    )

  assert Path( found ).is_file(), "ccrypt path does not point to a file"

  return found


def _run_ccrypt(
  mode_flag_ : str ,
  data_ : bytes ,
  password_ : str ,
) -> bytes:
  """
  Run ccrypt as a stdin to stdout filter.

  Args:
    mode_flag_ (str): `-e` for encryption or `-d` for decryption.
    data_ (bytes): Input bytes.
    password_ (str): Key handed over through the child environment.

  Returns:
    bytes: Output bytes produced by ccrypt.

  Raises:
    Wrong_Password_Error: If the key does not match.
    Crypto_Error: For any other ccrypt failure.
  """

  assert mode_flag_ in ( "-e", "-d" ), "mode_flag_ must be -e or -d"
  assert len( password_ ) > 0, "password_ must not be empty"

  child_env : dict[str, str] = os.environ.copy()
  child_env[ CCRYPT_KEY_ENV ] = password_

  try:
    completed : subprocess.CompletedProcess = subprocess.run(
      [ find_ccrypt(), mode_flag_, "-E", CCRYPT_KEY_ENV ],
      input=data_,
      capture_output=True,
      env=child_env,
      timeout=CCRYPT_TIMEOUT_SECONDS,
      check=False,
    )
  except subprocess.TimeoutExpired as error:
    raise Crypto_Error( "ccrypt timed out" ) from error

  if completed.returncode != 0:
    message : str = completed.stderr.decode( errors="replace" ).strip()
    if "key does not match" in message:
      raise Wrong_Password_Error( "wrong password" )
    raise Crypto_Error( message or "ccrypt failed" )

  return completed.stdout


def encrypt_bytes(
  data_ : bytes ,
  password_ : str ,
) -> bytes:
  """
  Encrypt bytes with ccrypt.

  Args:
    data_ (bytes): Plaintext.
    password_ (str): Non-empty password.

  Returns:
    bytes: ccrypt ciphertext.
  """

  encrypted : bytes = _run_ccrypt( "-e", data_, password_ )

  assert len( encrypted ) > 0, "ccrypt produced no output"

  return encrypted


def decrypt_bytes(
  data_ : bytes ,
  password_ : str ,
) -> bytes:
  """
  Decrypt ccrypt ciphertext.

  Args:
    data_ (bytes): Ciphertext.
    password_ (str): Non-empty password.

  Returns:
    bytes: Plaintext.

  Raises:
    Wrong_Password_Error: If the password is wrong.
    Crypto_Error: If the data is not valid ccrypt output.
  """

  if len( data_ ) == 0:
    raise Crypto_Error( "encrypted file is empty" )

  return _run_ccrypt( "-d", data_, password_ )


# ==============================================================================
# Unittest
if __name__ == "__main__":
  sample : bytes = b"unit test secret"
  assert decrypt_bytes( encrypt_bytes( sample, "pw" ), "pw" ) == sample
  print( "crypto self test passed" )
