"""Local only git repository that versions the encrypted secret files."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

GIT_TIMEOUT_SECONDS : float = 30.0
FALLBACK_NAME : str = "keyvault"
FALLBACK_EMAIL : str = "keyvault@localhost"
VAULT_GITIGNORE : str = "*\n!.gitignore\n!*.cpt\n!*.age\n"
RAGE_IGNORE_RULE : str = "!*.age"
CCRYPT_IGNORE_RULE : str = "!*.cpt"
FIELD_SEPARATOR : str = "\x1f"


class Git_Error( Exception ):
  """Raised when a git command fails."""


@dataclass( frozen=True )
class Revision:
  """One commit that touched a file."""

  commit : str
  short_commit : str
  date : str
  message : str


class Git_Store:
  """Git operations scoped to one secrets folder. No remote is ever used."""

  def __init__(
    self ,
    root_ : Path ,
  ) -> None:
    """
    Args:
      root_ (Path): Existing folder that holds the secrets.
    """

    assert root_.is_dir(), "root_ must be an existing directory"

    self.root : Path = root_.resolve()

  def _git(
    self ,
    args_ : list[str] ,
    input_ : bytes | None = None ,
    check_ : bool = True ,
  ) -> subprocess.CompletedProcess:
    """
    Run git inside the vault folder.

    Args:
      args_ (list[str]): Arguments after `git`.
      input_ (bytes, optional): Data for stdin.
      check_ (bool): Raise Git_Error on a non-zero exit when True.

    Returns:
      subprocess.CompletedProcess: Captured result with bytes output.
    """

    assert len( args_ ) > 0, "args_ must not be empty"

    command : list[str] = [ "git", "-C", str( self.root ) ] + args_

    try:
      completed : subprocess.CompletedProcess = subprocess.run(
        command,
        input=input_,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
      )
    except FileNotFoundError as error:
      raise Git_Error( "git was not found. Run `just install-system-deps`." ) from error
    except subprocess.TimeoutExpired as error:
      raise Git_Error( "git timed out" ) from error

    if check_ and completed.returncode != 0:
      message : str = completed.stderr.decode( errors="replace" ).strip()
      raise Git_Error( message or "git failed" )

    return completed

  def _identity_flags( self ) -> list[str]:
    """Return -c flags that supply an identity when none is configured."""

    flags : list[str] = []

    for key, fallback in (
      ( "user.name", FALLBACK_NAME ),
      ( "user.email", FALLBACK_EMAIL ),
    ):
      result : subprocess.CompletedProcess = self._git(
        [ "config", key ], check_=False
      )
      if result.stdout.strip() == b"":
        flags += [ "-c", f"{key}={fallback}" ]

    return flags

  def is_repository( self ) -> bool:
    """Return True when the folder itself is the top level of a repository."""

    result : subprocess.CompletedProcess = self._git(
      [ "rev-parse", "--show-toplevel" ], check_=False
    )

    if result.returncode != 0:
      return False

    top_level : Path = Path( result.stdout.decode().strip() ).resolve()

    return top_level == self.root

  def ensure_repository( self ) -> bool:
    """
    Create a repository with a restrictive .gitignore when none exists.

    Returns:
      bool: True when a new repository was created.
    """

    if self.is_repository():
      self.allow_rage_files()
      return False

    self._git( [ "init", "--quiet" ] )

    gitignore : Path = self.root / ".gitignore"
    if not gitignore.exists():
      gitignore.write_text( VAULT_GITIGNORE )
      self.commit_paths( [ ".gitignore" ], "init vault" )

    assert self.is_repository(), "repository creation failed"

    return True

  def allow_rage_files( self ) -> bool:
    """
    Let `.age` files through a .gitignore written before rage support.

    Only a .gitignore that already carries the `!*.cpt` rule is touched.

    Returns:
      bool: True when the rule was appended and committed.
    """

    gitignore : Path = self.root / ".gitignore"

    if not gitignore.is_file():
      return False

    lines : list[str] = gitignore.read_text().splitlines()
    if CCRYPT_IGNORE_RULE not in lines or RAGE_IGNORE_RULE in lines:
      return False

    gitignore.write_text( "\n".join( lines + [ RAGE_IGNORE_RULE ] ) + "\n" )
    self.commit_paths( [ ".gitignore" ], "allow rage files" )

    return True

  def is_tracked(
    self ,
    name_ : str ,
  ) -> bool:
    """Return True when name_ is in the index."""

    result : subprocess.CompletedProcess = self._git(
      [ "ls-files", "--error-unmatch", "--", name_ ], check_=False
    )

    return result.returncode == 0

  def commit_paths(
    self ,
    names_ : list[str] ,
    message_ : str ,
  ) -> None:
    """
    Stage the given paths and commit only those paths.

    Deleted paths are staged as removals. Nothing else in the folder is
    committed.

    Args:
      names_ (list[str]): File names relative to the vault root.
      message_ (str): Commit message.
    """

    assert len( names_ ) > 0, "names_ must not be empty"
    assert len( message_ ) > 0, "message_ must not be empty"

    for name in names_:
      exists : bool = ( self.root / name ).exists()
      if exists or self.is_tracked( name ):
        self._git( [ "add", "--force", "--all", "--", name ] )

    self._git(
      self._identity_flags()
      + [ "commit", "--quiet", "--no-gpg-sign", "-m", message_, "--" ]
      + names_
    )

  def history(
    self ,
    name_ : str ,
  ) -> list[Revision]:
    """
    List the commits that touched name_ from newest to oldest.

    Args:
      name_ (str): File name relative to the vault root.

    Returns:
      list[Revision]: Empty when the file has no history.
    """

    assert len( name_ ) > 0, "name_ must not be empty"

    log_format : str = FIELD_SEPARATOR.join( [ "%H", "%h", "%ad", "%s" ] )
    result : subprocess.CompletedProcess = self._git(
      [
        "log",
        f"--format={log_format}",
        "--date=format:%Y-%m-%d %H:%M:%S",
        "--",
        name_,
      ],
      check_=False,
    )

    if result.returncode != 0:
      return []

    revisions : list[Revision] = []

    for line in result.stdout.decode( errors="replace" ).splitlines():
      fields : list[str] = line.split( FIELD_SEPARATOR )
      if len( fields ) == 4:
        revisions.append( Revision( *fields ) )

    return revisions

  def read_at_revision(
    self ,
    commit_ : str ,
    name_ : str ,
  ) -> bytes:
    """
    Return the bytes of name_ as stored in commit_.

    Raises:
      Git_Error: If the file does not exist in that commit.
    """

    assert len( commit_ ) > 0, "commit_ must not be empty"

    result : subprocess.CompletedProcess = self._git(
      [ "show", f"{commit_}:{name_}" ]
    )

    return result.stdout


# ==============================================================================
# Unittest
if __name__ == "__main__":
  import tempfile

  with tempfile.TemporaryDirectory() as tmp:
    store : Git_Store = Git_Store( Path( tmp ) )
    assert store.ensure_repository()
    assert not store.ensure_repository()
    print( "git_store self test passed" )
