"""Secret folder model: list entries and run encrypt decrypt add delete."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from keyvault.crypto import (
  CCRYPT_SUFFIX,
  decrypt_bytes,
  encrypt_bytes,
)
from keyvault.git_store import Git_Store, Revision

HIDDEN_PREFIX : str = "."
RESERVED_NAMES : frozenset[str] = frozenset( { ".git", ".gitignore" } )


class Vault_Error( Exception ):
  """Raised for invalid vault operations such as name collisions."""


@dataclass( frozen=True )
class Entry:
  """One file listed in the vault."""

  name : str
  encrypted : bool
  size : int
  modified : str


def validate_entry_name(
  name_ : str ,
) -> str:
  """
  Validate a file name typed by the user.

  Args:
    name_ (str): Raw name.

  Returns:
    str: Stripped name.

  Raises:
    Vault_Error: If the name is empty or reserved or contains a path
      separator.
  """

  name : str = name_.strip()

  if name == "" or name in ( ".", ".." ):
    raise Vault_Error( "file name must not be empty" )
  if "/" in name or "\\" in name or "\x00" in name:
    raise Vault_Error( "file name must not contain path separators" )
  if name in RESERVED_NAMES:
    raise Vault_Error( f"{name} is reserved" )

  return name


def hidden_name(
  name_ : str ,
) -> str:
  """Return name_ with exactly one leading dot."""

  return HIDDEN_PREFIX + validate_entry_name( name_ ).lstrip( HIDDEN_PREFIX )


def encrypted_name_of(
  name_ : str ,
) -> str:
  """Return the hidden encrypted file name that backs name_."""

  if name_.endswith( CCRYPT_SUFFIX ):
    return name_

  return hidden_name( name_ ) + CCRYPT_SUFFIX


class Vault:
  """Operations on one folder of secrets with local git versioning."""

  def __init__(
    self ,
    root_ : Path ,
  ) -> None:
    """
    Args:
      root_ (Path): Existing folder. A git repository is created if absent.

    Raises:
      Vault_Error: If root_ is not an existing directory.
    """

    if not root_.is_dir():
      raise Vault_Error( f"{root_} is not a folder" )

    self.root : Path = root_.resolve()
    self.git : Git_Store = Git_Store( self.root )
    self.created_repository : bool = self.git.ensure_repository()

  def list_entries( self ) -> list[Entry]:
    """
    List regular files in the folder including hidden ones.

    The git metadata files are skipped. Entries sort by name ignoring the
    leading dot.

    Returns:
      list[Entry]: One entry per file. Encrypted means a .cpt suffix.
    """

    entries : list[Entry] = []

    for path in sorted(
      self.root.iterdir(),
      key=lambda p: p.name.lstrip( HIDDEN_PREFIX ).lower(),
    ):
      if path.name in RESERVED_NAMES or not path.is_file():
        continue
      stat = path.stat()
      entries.append(
        Entry(
          name=path.name,
          encrypted=path.suffix == CCRYPT_SUFFIX,
          size=stat.st_size,
          modified=datetime.fromtimestamp( stat.st_mtime ).strftime(
            "%Y-%m-%d %H:%M"
          ),
        )
      )

    return entries

  def _path(
    self ,
    name_ : str ,
  ) -> Path:
    """Resolve name_ inside the root and reject anything that escapes it."""

    name : str = validate_entry_name( name_ )
    path : Path = ( self.root / name ).resolve()

    if path.parent != self.root:
      raise Vault_Error( "file is outside of the vault folder" )

    return path

  def read_secret(
    self ,
    name_ : str ,
    password_ : str ,
  ) -> bytes:
    """
    Return the plaintext of an entry without writing anything to disk.

    Args:
      name_ (str): Entry name.
      password_ (str): Password. Ignored for plaintext entries.
    """

    path : Path = self._path( name_ )
    data : bytes = path.read_bytes()

    if path.suffix != CCRYPT_SUFFIX:
      return data

    return decrypt_bytes( data, password_ )

  def add_secret(
    self ,
    name_ : str ,
    secret_ : str ,
    password_ : str ,
  ) -> str:
    """
    Encrypt a typed secret straight to a new .cpt file and commit it.

    Args:
      name_ (str): File name. A leading dot and the `.cpt` suffix are
        added when missing so the file is hidden.
      secret_ (str): Secret text.
      password_ (str): Encryption password.

    Returns:
      str: Final file name.

    Raises:
      Vault_Error: If the file already exists.
    """

    name : str = hidden_name( name_ )
    if not name.endswith( CCRYPT_SUFFIX ):
      name += CCRYPT_SUFFIX

    path : Path = self._path( name )
    plain_twin : Path = self._path( name[ : -len( CCRYPT_SUFFIX ) ] )

    if path.exists() or plain_twin.exists():
      raise Vault_Error( f"{name} or its plaintext twin already exists" )

    path.write_bytes( encrypt_bytes( secret_.encode(), password_ ) )
    self.git.commit_paths( [ name ], name )

    assert path.is_file(), "encrypted file was not written"

    return name

  def encrypt_entry(
    self ,
    name_ : str ,
    password_ : str ,
  ) -> str:
    """
    Encrypt a plaintext entry to .name.cpt then remove the plaintext.

    The encrypted file is hidden through a leading dot.

    Returns:
      str: Name of the encrypted file.
    """

    path : Path = self._path( name_ )

    if path.suffix == CCRYPT_SUFFIX:
      raise Vault_Error( f"{path.name} is already encrypted" )

    target : Path = self._path( hidden_name( path.name ) + CCRYPT_SUFFIX )
    if target.exists():
      raise Vault_Error( f"{target.name} already exists" )

    target.write_bytes( encrypt_bytes( path.read_bytes(), password_ ) )
    path.unlink()
    self.git.commit_paths( [ target.name ], target.name )

    assert target.is_file() and not path.exists(), "encryption incomplete"

    return target.name

  def decrypt_entry(
    self ,
    name_ : str ,
    password_ : str ,
  ) -> str:
    """
    Decrypt .name.cpt to .name then remove the .cpt file.

    The plaintext is not committed. Git history keeps the encrypted
    versions.

    Returns:
      str: Name of the plaintext file.
    """

    path : Path = self._path( name_ )

    if path.suffix != CCRYPT_SUFFIX:
      raise Vault_Error( f"{path.name} is not encrypted" )

    target : Path = self._path( path.name[ : -len( CCRYPT_SUFFIX ) ] )
    if target.exists():
      raise Vault_Error( f"{target.name} already exists" )

    target.write_bytes( decrypt_bytes( path.read_bytes(), password_ ) )
    path.unlink()

    assert target.is_file() and not path.exists(), "decryption incomplete"

    return target.name

  def delete_entry(
    self ,
    name_ : str ,
    confirmation_ : str ,
  ) -> None:
    """
    Delete a file only when confirmation_ equals the file name exactly.

    Args:
      name_ (str): Entry name.
      confirmation_ (str): Name typed by the user.

    Raises:
      Vault_Error: If the confirmation differs or the file is missing.
    """

    path : Path = self._path( name_ )

    if confirmation_ != path.name:
      raise Vault_Error( "typed name does not match the file name" )
    if not path.is_file():
      raise Vault_Error( f"{path.name} does not exist" )

    tracked : bool = self.git.is_tracked( path.name )
    path.unlink()

    if tracked:
      self.git.commit_paths( [ path.name ], f"delete {path.name}" )

    assert not path.exists(), "file still present after deletion"

  def history(
    self ,
    name_ : str ,
  ) -> list[Revision]:
    """List commits of the encrypted file that backs name_."""

    path : Path = self._path( name_ )
    encrypted_name : str = encrypted_name_of( path.name )

    return self.git.history( encrypted_name )

  def read_revision(
    self ,
    name_ : str ,
    commit_ : str ,
    password_ : str ,
  ) -> bytes:
    """Decrypt the stored version of an entry at commit_."""

    path : Path = self._path( name_ )
    encrypted_name : str = encrypted_name_of( path.name )

    return decrypt_bytes(
      self.git.read_at_revision( commit_, encrypted_name ),
      password_,
    )


# ==============================================================================
# Unittest
if __name__ == "__main__":
  import tempfile

  with tempfile.TemporaryDirectory() as tmp:
    vault : Vault = Vault( Path( tmp ) )
    vault.add_secret( "demo", "value", "pw" )
    assert vault.read_secret( "demo.cpt", "pw" ) == b"value"
    print( "vault self test passed" )
