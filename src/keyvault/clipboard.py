"""System clipboard access through the tools of the host."""

import shutil
import subprocess
from typing import Optional

CLIPBOARD_TIMEOUT_SECONDS : float = 3.0
COPY_COMMANDS : tuple[tuple[str, ...], ...] = (
  ( "wl-copy", ),
  ( "xclip", "-selection", "clipboard" ),
  ( "xsel", "--clipboard", "--input" ),
  ( "pbcopy", ),
  ( "clip.exe", ),
)
PASTE_COMMANDS : tuple[tuple[str, ...], ...] = (
  ( "wl-paste", "--no-newline" ),
  ( "xclip", "-selection", "clipboard", "-o" ),
  ( "xsel", "--clipboard", "--output" ),
  ( "pbpaste", ),
)


def copy_text(
  text_ : str ,
) -> bool:
  """
  Place text_ on the system clipboard.

  Returns:
    bool: True when one of the clipboard tools accepted the text.
  """

  for command in COPY_COMMANDS:
    if shutil.which( command[ 0 ] ) is None:
      continue
    try:
      completed : subprocess.CompletedProcess = subprocess.run(
        list( command ),
        input=text_.encode(),
        capture_output=True,
        timeout=CLIPBOARD_TIMEOUT_SECONDS,
        check=False,
      )
    except ( subprocess.TimeoutExpired, OSError ):
      continue
    if completed.returncode == 0:
      return True

  return False


def read_text() -> Optional[str]:
  """
  Read the system clipboard.

  Returns:
    str: Clipboard text or None when no tool could read it.
  """

  for command in PASTE_COMMANDS:
    if shutil.which( command[ 0 ] ) is None:
      continue
    try:
      completed : subprocess.CompletedProcess = subprocess.run(
        list( command ),
        capture_output=True,
        timeout=CLIPBOARD_TIMEOUT_SECONDS,
        check=False,
      )
    except ( subprocess.TimeoutExpired, OSError ):
      continue
    if completed.returncode == 0:
      return completed.stdout.decode( errors="replace" )

  return None
