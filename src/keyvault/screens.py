"""Modal dialogs used by the KeyVault application."""

from pathlib import Path
from typing import Iterable, Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
  Button,
  DataTable,
  DirectoryTree,
  Input,
  Label,
  RadioButton,
  RadioSet,
  TextArea,
)

from keyvault.git_store import Revision

MODAL_CSS : str = """
{cls} {{
  align: center middle;
}}
{cls} > Vertical {{
  width: 80%;
  max-width: 100;
  height: auto;
  max-height: 90%;
  border: round $primary;
  background: $surface;
  padding: 1 2;
}}
{cls} Label {{
  margin-bottom: 1;
}}
{cls} Horizontal {{
  height: auto;
  align-horizontal: right;
  margin-top: 1;
}}
{cls} Button {{
  margin-left: 2;
}}
"""


class Password_Screen( ModalScreen[Optional[str]] ):
  """Ask for a password and optionally for its confirmation."""

  DEFAULT_CSS : str = MODAL_CSS.format( cls="Password_Screen" )
  BINDINGS : list[Binding] = [ Binding( "escape", "cancel", "Cancel" ) ]

  def __init__(
    self ,
    confirm_ : bool = False ,
    prompt_ : str = "Password" ,
  ) -> None:
    """
    Args:
      confirm_ (bool): Require the password to be typed twice.
      prompt_ (str): Heading shown above the input.
    """

    super().__init__()
    self.confirm : bool = confirm_
    self.prompt : str = prompt_

  def compose( self ) -> ComposeResult:
    """Build the dialog."""

    with Vertical():
      yield Label( self.prompt )
      yield Input( password=True, placeholder="password", id="password" )
      if self.confirm:
        yield Input(
          password=True, placeholder="repeat password", id="confirmation"
        )
      yield Label( "", id="error" )
      with Horizontal():
        yield Button( "OK", variant="primary", id="ok" )
        yield Button( "Cancel", id="cancel" )

  def on_mount( self ) -> None:
    """Focus the first input."""

    self.query_one( "#password", Input ).focus()

  def _submit( self ) -> None:
    """Validate the inputs and close the dialog."""

    password : str = self.query_one( "#password", Input ).value

    if password == "":
      self.query_one( "#error", Label ).update( "Password must not be empty." )
      return

    if self.confirm:
      repeated : str = self.query_one( "#confirmation", Input ).value
      if repeated != password:
        self.query_one( "#error", Label ).update( "Passwords differ." )
        return

    self.dismiss( password )

  @on( Input.Submitted )
  def _on_submitted( self ) -> None:
    """Enter submits the dialog."""

    self._submit()

  @on( Button.Pressed, "#ok" )
  def _on_ok( self ) -> None:
    """OK button."""

    self._submit()

  @on( Button.Pressed, "#cancel" )
  def action_cancel( self ) -> None:
    """Close without a password."""

    self.dismiss( None )


class Add_Secret_Screen( ModalScreen[Optional[tuple[str, str]]] ):
  """Collect a file name and a multi line secret."""

  DEFAULT_CSS : str = MODAL_CSS.format( cls="Add_Secret_Screen" ) + """
  Add_Secret_Screen TextArea {
    height: 6;
  }
  """
  BINDINGS : list[Binding] = [
    Binding( "escape", "cancel", "Cancel" ),
    Binding( "ctrl+s", "save", "Save" ),
  ]

  def __init__(
    self ,
    secret_ : str = "" ,
    suffix_ : str = ".cpt" ,
  ) -> None:
    """
    Args:
      secret_ (str): Text the secret box starts with.
      suffix_ (str): Encrypted suffix named in the heading.
    """

    super().__init__()
    self.initial_secret : str = secret_
    self.suffix : str = suffix_

  def compose( self ) -> ComposeResult:
    """Build the dialog."""

    with Vertical():
      yield Label( f"New secret. The file is stored as <name>{self.suffix}" )
      yield Input( placeholder="file name", id="name" )
      yield TextArea(
        self.initial_secret, id="secret", tab_behavior="focus"
      )
      yield Label( "", id="error" )
      with Horizontal():
        yield Button( "Save", variant="primary", id="save" )
        yield Button( "Cancel", id="cancel" )

  def on_mount( self ) -> None:
    """Focus the name input."""

    self.query_one( "#name", Input ).focus()

  @on( Button.Pressed, "#save" )
  def action_save( self ) -> None:
    """Validate and close the dialog."""

    name : str = self.query_one( "#name", Input ).value.strip()
    secret : str = self.query_one( "#secret", TextArea ).text

    if name == "":
      self.query_one( "#error", Label ).update( "File name is required." )
      return
    if secret == "":
      self.query_one( "#error", Label ).update( "Secret is empty." )
      return

    self.dismiss( ( name, secret ) )

  @on( Button.Pressed, "#cancel" )
  def action_cancel( self ) -> None:
    """Close without saving."""

    self.dismiss( None )


class Delete_Screen( ModalScreen[Optional[str]] ):
  """Require the exact file name before a deletion proceeds."""

  DEFAULT_CSS : str = MODAL_CSS.format( cls="Delete_Screen" )
  BINDINGS : list[Binding] = [ Binding( "escape", "cancel", "Cancel" ) ]

  def __init__(
    self ,
    name_ : str ,
  ) -> None:
    """
    Args:
      name_ (str): File that would be deleted.
    """

    assert len( name_ ) > 0, "name_ must not be empty"

    super().__init__()
    self.target_name : str = name_

  def compose( self ) -> ComposeResult:
    """Build the dialog."""

    with Vertical():
      yield Label( f"Delete {self.target_name}. This cannot be undone." )
      yield Label( "Type the exact file name to confirm:" )
      yield Input( placeholder=self.target_name, id="confirmation" )
      with Horizontal():
        yield Button(
          "Delete", variant="error", id="delete", disabled=True
        )
        yield Button( "Cancel", id="cancel" )

  def on_mount( self ) -> None:
    """Focus the confirmation input."""

    self.query_one( "#confirmation", Input ).focus()

  @on( Input.Changed )
  def _on_changed(
    self ,
    event_ : Input.Changed ,
  ) -> None:
    """Enable the delete button only on an exact match."""

    self.query_one( "#delete", Button ).disabled = (
      event_.value != self.target_name
    )

  @on( Input.Submitted )
  @on( Button.Pressed, "#delete" )
  def _on_confirm( self ) -> None:
    """Close with the typed name when it matches."""

    typed : str = self.query_one( "#confirmation", Input ).value

    if typed == self.target_name:
      self.dismiss( typed )

  @on( Button.Pressed, "#cancel" )
  def action_cancel( self ) -> None:
    """Close without deleting."""

    self.dismiss( None )


class History_Screen( ModalScreen[Optional[Revision]] ):
  """List the git history of a file and return the chosen revision."""

  DEFAULT_CSS : str = MODAL_CSS.format( cls="History_Screen" ) + """
  History_Screen DataTable {
    height: 14;
  }
  """
  BINDINGS : list[Binding] = [ Binding( "escape", "cancel", "Close" ) ]

  def __init__(
    self ,
    name_ : str ,
    revisions_ : Iterable[Revision] ,
  ) -> None:
    """
    Args:
      name_ (str): File name shown in the heading.
      revisions_ (Iterable[Revision]): Newest first.
    """

    super().__init__()
    self.file_name : str = name_
    self.revisions : list[Revision] = list( revisions_ )

  def compose( self ) -> ComposeResult:
    """Build the dialog."""

    with Vertical():
      yield Label(
        f"History of {self.file_name}. Enter shows the decrypted version."
      )
      yield DataTable( cursor_type="row", id="revisions" )
      with Horizontal():
        yield Button( "Close", id="cancel" )

  def on_mount( self ) -> None:
    """Fill the table."""

    table : DataTable = self.query_one( "#revisions", DataTable )
    table.add_columns( "Commit", "Date", "Message" )

    for revision in self.revisions:
      table.add_row(
        revision.short_commit,
        revision.date,
        revision.message,
        key=revision.commit,
      )

    if len( self.revisions ) == 0:
      self.query_one( Label ).update( f"No history for {self.file_name}." )

    table.focus()

  @on( DataTable.RowSelected )
  def _on_row_selected(
    self ,
    event_ : DataTable.RowSelected ,
  ) -> None:
    """Return the selected revision."""

    event_.stop()

    for revision in self.revisions:
      if revision.commit == event_.row_key.value:
        self.dismiss( revision )
        return

  @on( Button.Pressed, "#cancel" )
  def action_cancel( self ) -> None:
    """Close the dialog."""

    self.dismiss( None )


class Rename_Screen( ModalScreen[Optional[str]] ):
  """Ask for the new name of a file."""

  DEFAULT_CSS : str = MODAL_CSS.format( cls="Rename_Screen" )
  BINDINGS : list[Binding] = [ Binding( "escape", "cancel", "Cancel" ) ]

  def __init__(
    self ,
    name_ : str ,
    encrypted_ : bool = False ,
  ) -> None:
    """
    Args:
      name_ (str): Current file name.
      encrypted_ (bool): Encrypted files keep their dot and suffix.
    """

    assert len( name_ ) > 0, "name_ must not be empty"

    super().__init__()
    self.current_name : str = name_
    self.encrypted : bool = encrypted_

  def compose( self ) -> ComposeResult:
    """Build the dialog."""

    hint : str = (
      " The leading dot and the suffix are kept." if self.encrypted else ""
    )

    with Vertical():
      yield Label( f"Rename {self.current_name}.{hint}" )
      yield Input( value=self.current_name, id="new-name" )
      yield Label( "", id="error" )
      with Horizontal():
        yield Button( "Rename", variant="primary", id="rename" )
        yield Button( "Cancel", id="cancel" )

  def on_mount( self ) -> None:
    """Focus the input."""

    self.query_one( "#new-name", Input ).focus()

  @on( Input.Submitted )
  @on( Button.Pressed, "#rename" )
  def _on_rename( self ) -> None:
    """Close with the typed name when it is not empty."""

    typed : str = self.query_one( "#new-name", Input ).value.strip()

    if typed == "":
      self.query_one( "#error", Label ).update( "Name is required." )
      return

    self.dismiss( typed )

  @on( Button.Pressed, "#cancel" )
  def action_cancel( self ) -> None:
    """Close without renaming."""

    self.dismiss( None )


class Permissions_Screen(
  ModalScreen[Optional[tuple[str, str, str]]]
):
  """Edit the mode and the owner and the group of files (chmod and chown)."""

  DEFAULT_CSS : str = MODAL_CSS.format( cls="Permissions_Screen" )
  BINDINGS : list[Binding] = [ Binding( "escape", "cancel", "Cancel" ) ]

  def __init__(
    self ,
    names_ : list[str] ,
    mode_ : str = "600" ,
    owner_ : str = "" ,
    group_ : str = "" ,
  ) -> None:
    """
    Args:
      names_ (list[str]): Files that receive the change.
      mode_ (str): Octal mode shown in the mode input.
      owner_ (str): Current owner shown as placeholder.
      group_ (str): Current group shown as placeholder.
    """

    assert len( names_ ) > 0, "names_ must not be empty"

    super().__init__()
    self.names : list[str] = names_
    self.initial_mode : str = mode_
    self.current_owner : str = owner_
    self.current_group : str = group_

  def compose( self ) -> ComposeResult:
    """Build the dialog."""

    subject : str = (
      self.names[ 0 ]
      if len( self.names ) == 1
      else f"{len( self.names )} files"
    )

    with Vertical():
      yield Label( f"Permissions of {subject}. Empty fields stay unchanged." )
      yield Label( "Mode (octal, for example 600):" )
      yield Input( value=self.initial_mode, id="mode" )
      yield Label( "Owner (name or id, usually needs root):" )
      yield Input( placeholder=self.current_owner, id="owner" )
      yield Label( "Group (name or id):" )
      yield Input( placeholder=self.current_group, id="group" )
      yield Label( "", id="error" )
      with Horizontal():
        yield Button( "Apply", variant="primary", id="apply" )
        yield Button( "Cancel", id="cancel" )

  def on_mount( self ) -> None:
    """Focus the mode input."""

    self.query_one( "#mode", Input ).focus()

  @on( Input.Submitted )
  @on( Button.Pressed, "#apply" )
  def _on_apply( self ) -> None:
    """Close the dialog with the three typed values."""

    mode : str = self.query_one( "#mode", Input ).value.strip()
    owner : str = self.query_one( "#owner", Input ).value.strip()
    group : str = self.query_one( "#group", Input ).value.strip()

    if mode == "" and owner == "" and group == "":
      self.query_one( "#error", Label ).update( "Nothing to change." )
      return

    self.dismiss( ( mode, owner, group ) )

  @on( Button.Pressed, "#cancel" )
  def action_cancel( self ) -> None:
    """Close without changes."""

    self.dismiss( None )


class Export_Screen( ModalScreen[Optional[tuple[str, str]]] ):
  """Ask for the variable name and for the export format."""

  DEFAULT_CSS : str = MODAL_CSS.format( cls="Export_Screen" )
  BINDINGS : list[Binding] = [ Binding( "escape", "cancel", "Cancel" ) ]
  FORMAT_ENV : str = "env"
  FORMAT_EXPORT : str = "export"

  def __init__(
    self ,
    file_name_ : str ,
    default_name_ : str = "" ,
  ) -> None:
    """
    Args:
      file_name_ (str): Secret that is exported.
      default_name_ (str): Suggested variable name.
    """

    super().__init__()
    self.file_name : str = file_name_
    self.default_name : str = default_name_

  def compose( self ) -> ComposeResult:
    """Build the dialog."""

    with Vertical():
      yield Label( f"Export the decrypted secret of {self.file_name}." )
      yield Label( "Variable name (name_secret):" )
      yield Input( value=self.default_name, id="variable" )
      yield RadioSet(
        RadioButton( ".env file in the current directory", value=True ),
        RadioButton( "export command for the bash environment" ),
        id="format",
      )
      yield Label( "", id="error" )
      with Horizontal():
        yield Button( "Export", variant="primary", id="export" )
        yield Button( "Cancel", id="cancel" )

  def on_mount( self ) -> None:
    """Focus the name input."""

    self.query_one( "#variable", Input ).focus()

  @on( Input.Submitted )
  @on( Button.Pressed, "#export" )
  def _on_export( self ) -> None:
    """Close the dialog with the name and the chosen format."""

    variable : str = self.query_one( "#variable", Input ).value.strip()
    chosen : int = self.query_one( "#format", RadioSet ).pressed_index
    kind : str = self.FORMAT_ENV if chosen <= 0 else self.FORMAT_EXPORT

    if variable == "":
      self.query_one( "#error", Label ).update( "Variable name is required." )
      return

    self.dismiss( ( variable, kind ) )

  @on( Button.Pressed, "#cancel" )
  def action_cancel( self ) -> None:
    """Close without exporting."""

    self.dismiss( None )


class Folder_Directory_Tree( DirectoryTree ):
  """Directory tree that lists visible folders only."""

  def filter_paths(
    self ,
    paths : Iterable[Path] ,
  ) -> list[Path]:
    """Keep directories that do not start with a dot."""

    return [
      path
      for path in paths
      if path.is_dir() and not path.name.startswith( "." )
    ]


class Folder_Screen( ModalScreen[Optional[Path]] ):
  """Choose the folder that holds the secrets."""

  DEFAULT_CSS : str = MODAL_CSS.format( cls="Folder_Screen" ) + """
  Folder_Screen Folder_Directory_Tree {
    height: 16;
  }
  """
  BINDINGS : list[Binding] = [ Binding( "escape", "cancel", "Cancel" ) ]

  def __init__(
    self ,
    start_ : Path ,
  ) -> None:
    """
    Args:
      start_ (Path): Folder pre-filled in the path input.
    """

    super().__init__()
    self.start : Path = start_

  def compose( self ) -> ComposeResult:
    """Build the dialog."""

    with Vertical():
      yield Label( "Select the folder with the secrets or type its path." )
      yield Input( value=str( self.start ), id="path" )
      yield Folder_Directory_Tree( str( Path.home() ) )
      yield Label( "", id="error" )
      with Horizontal():
        yield Button( "Open", variant="primary", id="open" )
        yield Button( "Cancel", id="cancel" )

  def on_mount( self ) -> None:
    """Focus the path input."""

    self.query_one( "#path", Input ).focus()

  @on( DirectoryTree.DirectorySelected )
  def _on_directory_selected(
    self ,
    event_ : DirectoryTree.DirectorySelected ,
  ) -> None:
    """Copy the clicked folder into the path input."""

    self.query_one( "#path", Input ).value = str( event_.path )

  @on( Input.Submitted )
  @on( Button.Pressed, "#open" )
  def _on_open( self ) -> None:
    """Validate the typed path and close the dialog."""

    typed : Path = Path( self.query_one( "#path", Input ).value ).expanduser()

    if not typed.is_dir():
      self.query_one( "#error", Label ).update( f"{typed} is not a folder." )
      return

    self.dismiss( typed.resolve() )

  @on( Button.Pressed, "#cancel" )
  def action_cancel( self ) -> None:
    """Close without choosing."""

    self.dismiss( None )
