"""Secret folder model: list entries and run encrypt decrypt add delete."""

import os
import shutil
import stat as stat_module
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from keyvault.crypto import (
  BACKEND_CCRYPT,
  BACKEND_SUFFIXES,
  BACKENDS,
  ENCRYPTED_SUFFIXES,
  backend_for_name,
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
  mode : str = ""
  owner : str = ""
  group : str = ""


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


def is_encrypted_name(
  name_ : str ,
) -> bool:
  """Return True when name_ ends with a known encrypted suffix."""

  return name_.endswith( ENCRYPTED_SUFFIXES )


def strip_encrypted_suffix(
  name_ : str ,
) -> str:
  """Return name_ without its encrypted suffix."""

  for suffix in ENCRYPTED_SUFFIXES:
    if name_.endswith( suffix ):
      return name_[ : -len( suffix ) ]

  return name_


def encrypted_name_of(
  name_ : str ,
  backend_ : str = BACKEND_CCRYPT ,
) -> str:
  """Return the hidden encrypted file name that backs name_."""

  if is_encrypted_name( name_ ):
    return name_

  return hidden_name( name_ ) + BACKEND_SUFFIXES[ backend_ ]


def parse_mode(
  mode_ : str ,
) -> int:
  """
  Convert an octal string such as `640` or `0o640` to an integer.

  Raises:
    Vault_Error: If mode_ is not an octal number up to 7777.
  """

  text : str = mode_.strip().lower().removeprefix( "0o" )

  if text == "" or any( c not in "01234567" for c in text ) or len( text ) > 4:
    raise Vault_Error( f"{mode_!r} is not an octal mode such as 600" )

  return int( text, 8 )


def lookup_owner(
  uid_ : int ,
) -> str:
  """Return the user name of uid_ or the number when unknown."""

  try:
    import pwd

    return pwd.getpwuid( uid_ ).pw_name
  except ( ImportError, KeyError ):
    return str( uid_ )


def lookup_group(
  gid_ : int ,
) -> str:
  """Return the group name of gid_ or the number when unknown."""

  try:
    import grp

    return grp.getgrgid( gid_ ).gr_name
  except ( ImportError, KeyError ):
    return str( gid_ )


class Vault:
  """Operations on one folder of secrets with local git versioning."""

  def __init__(
    self ,
    root_ : Path ,
    backend_ : str = BACKEND_CCRYPT ,
  ) -> None:
    """
    Args:
      root_ (Path): Existing folder. A git repository is created if absent.
      backend_ (str): Backend used to create new ciphertext.

    Raises:
      Vault_Error: If root_ is not an existing directory or backend_ is
        unknown.
    """

    if not root_.is_dir():
      raise Vault_Error( f"{root_} is not a folder" )
    if backend_ not in BACKENDS:
      raise Vault_Error( f"unknown backend {backend_}" )

    self.backend : str = backend_

    self.root : Path = root_.resolve()
    self.git : Git_Store = Git_Store( self.root )
    self.created_repository : bool = self.git.ensure_repository()

  def list_entries( self ) -> list[Entry]:
    """
    List regular files in the folder including hidden ones.

    The git metadata files are skipped. Entries sort by name ignoring the
    leading dot.

    Returns:
      list[Entry]: One entry per file. Encrypted means a .cpt or .age suffix.
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
          encrypted=is_encrypted_name( path.name ),
          size=stat.st_size,
          modified=datetime.fromtimestamp( stat.st_mtime ).strftime(
            "%Y-%m-%d %H:%M"
          ),
          mode=stat_module.filemode( stat.st_mode ),
          owner=lookup_owner( stat.st_uid ),
          group=lookup_group( stat.st_gid ),
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

    if not is_encrypted_name( path.name ):
      return data

    return decrypt_bytes( data, password_, backend_for_name( path.name ) )

  def add_secret(
    self ,
    name_ : str ,
    secret_ : str ,
    password_ : str ,
  ) -> str:
    """
    Encrypt a typed secret straight to a new .cpt file and commit it.

    Args:
      name_ (str): File name. A leading dot and the backend suffix are
        added when missing so the file is hidden.
      secret_ (str): Secret text.
      password_ (str): Encryption password.

    Returns:
      str: Final file name.

    Raises:
      Vault_Error: If the file already exists.
    """

    name : str = hidden_name( name_ )
    if not is_encrypted_name( name ):
      name += BACKEND_SUFFIXES[ self.backend ]

    path : Path = self._path( name )
    plain_twin : Path = self._path( strip_encrypted_suffix( name ) )

    if path.exists() or plain_twin.exists():
      raise Vault_Error( f"{name} or its plaintext twin already exists" )

    path.write_bytes(
      encrypt_bytes( secret_.encode(), password_, backend_for_name( name ) )
    )
    self.git.commit_paths( [ name ], name )

    assert path.is_file(), "encrypted file was not written"

    return name

  def encrypt_entry(
    self ,
    name_ : str ,
    password_ : str ,
  ) -> str:
    """
    Encrypt a plaintext entry to .name.<suffix> then remove the plaintext.

    The encrypted file is hidden through a leading dot.

    Returns:
      str: Name of the encrypted file.
    """

    path : Path = self._path( name_ )

    if is_encrypted_name( path.name ):
      raise Vault_Error( f"{path.name} is already encrypted" )

    target_name : str = hidden_name( path.name ) + BACKEND_SUFFIXES[
      self.backend
    ]
    target : Path = self._path( target_name )
    if target.exists():
      raise Vault_Error( f"{target.name} already exists" )

    target.write_bytes(
      encrypt_bytes( path.read_bytes(), password_, self.backend )
    )
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
    Decrypt .name.cpt or .name.age to .name then remove the encrypted file.

    The plaintext is not committed. Git history keeps the encrypted
    versions.

    Returns:
      str: Name of the plaintext file.
    """

    path : Path = self._path( name_ )

    if not is_encrypted_name( path.name ):
      raise Vault_Error( f"{path.name} is not encrypted" )

    target : Path = self._path( strip_encrypted_suffix( path.name ) )
    if target.exists():
      raise Vault_Error( f"{target.name} already exists" )

    target.write_bytes(
      decrypt_bytes(
        path.read_bytes(), password_, backend_for_name( path.name )
      )
    )
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

    for encrypted_name in self._encrypted_candidates( path.name ):
      revisions : list[Revision] = self.git.history( encrypted_name )
      if len( revisions ) > 0:
        return revisions

    return []

  def read_revision(
    self ,
    name_ : str ,
    commit_ : str ,
    password_ : str ,
  ) -> bytes:
    """Decrypt the stored version of an entry at commit_."""

    path : Path = self._path( name_ )

    for encrypted_name in self._encrypted_candidates( path.name ):
      if len( self.git.history( encrypted_name ) ) > 0:
        return decrypt_bytes(
          self.git.read_at_revision( commit_, encrypted_name ),
          password_,
          backend_for_name( encrypted_name ),
        )

    raise Vault_Error( f"{path.name} has no history" )

  def _encrypted_candidates(
    self ,
    name_ : str ,
  ) -> list[str]:
    """Encrypted names that can back name_ with the active backend first."""

    if is_encrypted_name( name_ ):
      return [ name_ ]

    ordered : list[str] = [ self.backend ] + [
      b for b in BACKENDS if b != self.backend
    ]

    return [ encrypted_name_of( name_, backend ) for backend in ordered ]

  def rename_entry(
    self ,
    name_ : str ,
    new_name_ : str ,
  ) -> str:
    """
    Rename an entry and commit the rename when the file is tracked.

    Encrypted entries keep their suffix and stay hidden. Plaintext entries
    take the typed name as is.

    Args:
      name_ (str): Current entry name.
      new_name_ (str): New name typed by the user.

    Returns:
      str: Final file name.

    Raises:
      Vault_Error: If the name is invalid or the target exists.
    """

    path : Path = self._path( name_ )

    if not path.is_file():
      raise Vault_Error( f"{path.name} does not exist" )

    new_name : str = validate_entry_name( new_name_ )
    if is_encrypted_name( path.name ):
      suffix : str = BACKEND_SUFFIXES[ backend_for_name( path.name ) ]
      new_name = hidden_name( strip_encrypted_suffix( new_name ) ) + suffix

    target : Path = self._path( new_name )

    if target.name == path.name:
      raise Vault_Error( "the new name equals the current name" )
    if target.exists():
      raise Vault_Error( f"{target.name} already exists" )

    tracked : bool = self.git.is_tracked( path.name )
    path.rename( target )

    if tracked:
      self.git.commit_paths(
        [ path.name, target.name ], f"rename {path.name} to {target.name}"
      )

    assert target.is_file() and not path.exists(), "rename incomplete"

    return target.name

  def octal_mode(
    self ,
    name_ : str ,
  ) -> str:
    """Return the permission bits of an entry as octal text such as 600."""

    return format( self._path( name_ ).stat().st_mode & 0o7777, "o" )

  def set_permissions(
    self ,
    name_ : str ,
    mode_ : Optional[str] = None ,
    owner_ : Optional[str] = None ,
    group_ : Optional[str] = None ,
  ) -> None:
    """
    Run chmod and chown on one entry.

    Args:
      name_ (str): Entry name.
      mode_ (str, optional): Octal mode such as `600`. None keeps the mode.
      owner_ (str, optional): User name or id. None or empty keeps it.
      group_ (str, optional): Group name or id. None or empty keeps it.

    Raises:
      Vault_Error: If a value is invalid or the system refuses the change.
    """

    path : Path = self._path( name_ )
    owner : Optional[str] = ( owner_ or "" ).strip() or None
    group : Optional[str] = ( group_ or "" ).strip() or None
    mode : Optional[int] = None

    if mode_ is not None and mode_.strip() != "":
      mode = parse_mode( mode_ )
    if not path.is_file():
      raise Vault_Error( f"{path.name} does not exist" )
    if ( owner or group ) and not hasattr( os, "chown" ):
      raise Vault_Error( "chown is not available on this system" )

    try:
      if mode is not None:
        os.chmod( path, mode )
      if owner or group:
        shutil.chown( path, user=owner, group=group )
    except ( LookupError, PermissionError, OSError ) as error:
      raise Vault_Error( f"cannot change {path.name}: {error}" ) from error


# ==============================================================================
# Unittest
if __name__ == "__main__":
  import tempfile

  with tempfile.TemporaryDirectory() as tmp:
    vault : Vault = Vault( Path( tmp ) )
    vault.add_secret( "demo", "value", "pw" )
    assert vault.read_secret( "demo.cpt", "pw" ) == b"value"
    print( "vault self test passed" )
