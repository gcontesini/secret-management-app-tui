"""Thin wrappers around the ccrypt and rage command line tools.

ccrypt receives the password through an environment variable that only
exists in the child process. rage only reads passphrases from a terminal, so
the child process gets a private pseudo terminal that answers its prompts.
Neither tool receives the password on the command line and plaintext never
touches the disk.
"""

import fcntl
import os
import pty
import select
import shutil
import subprocess
import sys
import termios
import threading
import time
from pathlib import Path
from typing import Optional

CCRYPT_KEY_ENV : str = "KEYVAULT_CCRYPT_KEY"
CCRYPT_SUFFIX : str = ".cpt"
RAGE_SUFFIX : str = ".age"
CCRYPT_TIMEOUT_SECONDS : float = 30.0
BACKEND_CCRYPT : str = "ccrypt"
BACKEND_RAGE : str = "rage"
BACKENDS : tuple[str, ...] = ( BACKEND_CCRYPT, BACKEND_RAGE )
BACKEND_SUFFIXES : dict[str, str] = {
  BACKEND_CCRYPT: CCRYPT_SUFFIX,
  BACKEND_RAGE: RAGE_SUFFIX,
}
ENCRYPTED_SUFFIXES : tuple[str, ...] = tuple( BACKEND_SUFFIXES.values() )
RAGE_WRONG_PASSWORD_HINTS : tuple[str, ...] = (
  "incorrect passphrase",
  "decryption failed",
  "bad mac",
)


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


def find_rage() -> str:
  """
  Locate the rage executable.

  Returns:
    str: Absolute path to rage.

  Raises:
    Crypto_Error: If rage cannot be found.
  """

  executable_name : str = "rage.exe" if os.name == "nt" else "rage"
  bundle_dir : Optional[str] = getattr( sys, "_MEIPASS", None )

  if bundle_dir is not None:
    bundled : Path = Path( bundle_dir ) / executable_name
    if bundled.is_file():
      return str( bundled )

  found : Optional[str] = shutil.which( "rage" )

  if found is None:
    raise Crypto_Error(
      "rage was not found. Install it from https://github.com/str4d/rage"
    )

  return found


def backend_for_name(
  name_ : str ,
) -> str:
  """Return the backend that owns the encrypted file name_ or raise."""

  for backend, suffix in BACKEND_SUFFIXES.items():
    if name_.endswith( suffix ):
      return backend

  raise Crypto_Error( f"{name_} has no known encrypted suffix" )


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


def _run_rage(
  mode_flag_ : str ,
  data_ : bytes ,
  password_ : str ,
) -> bytes:
  """
  Run rage as a stdin to stdout filter with a passphrase.

  The child process becomes the session leader of a pseudo terminal. Every
  passphrase prompt written to that terminal is answered with password_.

  Args:
    mode_flag_ (str): `-e` for encryption or `-d` for decryption.
    data_ (bytes): Input bytes.
    password_ (str): Passphrase typed into the pseudo terminal.

  Returns:
    bytes: Output bytes produced by rage.

  Raises:
    Wrong_Password_Error: If rage rejects the passphrase.
    Crypto_Error: For any other rage failure or a timeout.
  """

  assert mode_flag_ in ( "-e", "-d" ), "mode_flag_ must be -e or -d"
  assert len( password_ ) > 0, "password_ must not be empty"
  assert os.name != "nt", "rage passphrases need a POSIX terminal"

  command : list[str] = [ find_rage(), mode_flag_ ]
  if mode_flag_ == "-e":
    command.append( "-p" )

  master_fd, slave_fd = pty.openpty()

  def attach_terminal() -> None:
    os.setsid()
    fcntl.ioctl( slave_fd, termios.TIOCSCTTY, 0 )

  process : subprocess.Popen = subprocess.Popen(
    command,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    preexec_fn=attach_terminal,
    close_fds=True,
  )

  answers_sent : int = 0
  answers_limit : int = 2 if mode_flag_ == "-e" else 1
  deadline : float = time.monotonic() + CCRYPT_TIMEOUT_SECONDS
  stdout_data : bytes = b""
  stderr_data : bytes = b""

  try:
    def pump() -> None:
      nonlocal stdout_data, stderr_data
      stdout_data, stderr_data = process.communicate( input=data_ )

    pump_thread : threading.Thread = threading.Thread( target=pump )
    pump_thread.start()

    while pump_thread.is_alive() and time.monotonic() < deadline:
      ready, _, _ = select.select( [ master_fd ], [], [], 0.05 )
      if master_fd in ready:
        try:
          prompt : bytes = os.read( master_fd, 4096 )
        except OSError:
          continue
        if b":" in prompt and answers_sent < answers_limit:
          os.write( master_fd, password_.encode() + b"\n" )
          answers_sent += 1

    pump_thread.join( timeout=max( deadline - time.monotonic(), 0.1 ) )

    if pump_thread.is_alive():
      process.kill()
      pump_thread.join()
      raise Crypto_Error( "rage timed out" )
  finally:
    os.close( master_fd )
    os.close( slave_fd )

  if process.returncode != 0:
    message : str = stderr_data.decode( errors="replace" ).strip()
    if any( hint in message.lower() for hint in RAGE_WRONG_PASSWORD_HINTS ):
      raise Wrong_Password_Error( "wrong password" )
    raise Crypto_Error( message or "rage failed" )

  return stdout_data


def encrypt_bytes(
  data_ : bytes ,
  password_ : str ,
  backend_ : str = BACKEND_CCRYPT ,
) -> bytes:
  """
  Encrypt bytes with the chosen backend.

  Args:
    data_ (bytes): Plaintext.
    password_ (str): Non-empty password.
    backend_ (str): `ccrypt` or `rage`.

  Returns:
    bytes: Ciphertext.
  """

  assert backend_ in BACKENDS, "unknown backend_"

  runner = _run_rage if backend_ == BACKEND_RAGE else _run_ccrypt
  encrypted : bytes = runner( "-e", data_, password_ )

  assert len( encrypted ) > 0, "ccrypt produced no output"

  return encrypted


def decrypt_bytes(
  data_ : bytes ,
  password_ : str ,
  backend_ : str = BACKEND_CCRYPT ,
) -> bytes:
  """
  Decrypt ciphertext of the chosen backend.

  Args:
    data_ (bytes): Ciphertext.
    password_ (str): Non-empty password.
    backend_ (str): `ccrypt` or `rage`.

  Returns:
    bytes: Plaintext.

  Raises:
    Wrong_Password_Error: If the password is wrong.
    Crypto_Error: If the data is not valid ccrypt output.
  """

  if len( data_ ) == 0:
    raise Crypto_Error( "encrypted file is empty" )

  assert backend_ in BACKENDS, "unknown backend_"

  runner = _run_rage if backend_ == BACKEND_RAGE else _run_ccrypt

  return runner( "-d", data_, password_ )


# ==============================================================================
# Unittest
if __name__ == "__main__":
  sample : bytes = b"unit test secret"
  assert decrypt_bytes( encrypt_bytes( sample, "pw" ), "pw" ) == sample
  print( "crypto self test passed" )
