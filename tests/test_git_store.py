"""Tests for the local git store."""

import subprocess
from pathlib import Path

import pytest

from keyvault.git_store import Git_Error, Git_Store


def test_creates_repository_once( secrets_dir : Path ) -> None:
  store : Git_Store = Git_Store( secrets_dir )

  assert store.ensure_repository() is True
  assert store.ensure_repository() is False
  assert ( secrets_dir / ".gitignore" ).is_file()


def test_commit_message_and_history( secrets_dir : Path ) -> None:
  store : Git_Store = Git_Store( secrets_dir )
  store.ensure_repository()
  ( secrets_dir / "a.cpt" ).write_bytes( b"v1" )
  store.commit_paths( [ "a.cpt" ], "a.cpt" )
  ( secrets_dir / "a.cpt" ).write_bytes( b"v2" )
  store.commit_paths( [ "a.cpt" ], "a.cpt update" )

  revisions = store.history( "a.cpt" )

  assert [ r.message for r in revisions ] == [ "a.cpt update", "a.cpt" ]
  assert store.read_at_revision( revisions[ 1 ].commit, "a.cpt" ) == b"v1"


def test_plaintext_is_never_committed( secrets_dir : Path ) -> None:
  store : Git_Store = Git_Store( secrets_dir )
  store.ensure_repository()
  ( secrets_dir / "plain.txt" ).write_text( "leak" )
  ( secrets_dir / "b.cpt" ).write_bytes( b"x" )
  store.commit_paths( [ "b.cpt" ], "b.cpt" )

  tracked : str = subprocess.run(
    [ "git", "-C", str( secrets_dir ), "ls-files" ],
    capture_output=True, text=True, check=True,
  ).stdout.split()

  assert "plain.txt" not in tracked and "b.cpt" in tracked


def test_history_of_unknown_file_is_empty( secrets_dir : Path ) -> None:
  store : Git_Store = Git_Store( secrets_dir )
  store.ensure_repository()

  assert store.history( "missing.cpt" ) == []


def test_read_missing_revision_raises( secrets_dir : Path ) -> None:
  store : Git_Store = Git_Store( secrets_dir )
  store.ensure_repository()

  with pytest.raises( Git_Error ):
    store.read_at_revision( "HEAD", "missing.cpt" )


def test_commit_works_without_git_identity(
  secrets_dir : Path , monkeypatch : pytest.MonkeyPatch , tmp_path : Path
) -> None:
  monkeypatch.setenv( "HOME", str( tmp_path ) )
  monkeypatch.setenv( "GIT_CONFIG_GLOBAL", "/dev/null" )
  monkeypatch.setenv( "GIT_CONFIG_NOSYSTEM", "1" )
  store : Git_Store = Git_Store( secrets_dir )
  store.ensure_repository()
  ( secrets_dir / "c.cpt" ).write_bytes( b"x" )
  store.commit_paths( [ "c.cpt" ], "c.cpt" )

  assert len( store.history( "c.cpt" ) ) == 1


def test_existing_parent_repo_is_not_reused( tmp_path : Path ) -> None:
  subprocess.run( [ "git", "init", "-q", str( tmp_path ) ], check=True )
  child : Path = tmp_path / "child"
  child.mkdir()
  store : Git_Store = Git_Store( child )

  assert store.is_repository() is False
  assert store.ensure_repository() is True
