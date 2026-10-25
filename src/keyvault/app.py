"""Textual application that manages a folder of ccrypt secrets."""

from pathlib import Path
from typing import Optional

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.theme import Theme
from textual.widgets import DataTable, Footer, Header, RichLog, Static

from keyvault.config import load_palette, save_last_folder
from keyvault.crypto import Crypto_Error, Wrong_Password_Error
from keyvault.git_store import Git_Error, Revision
from keyvault.screens import (
  Add_Secret_Screen,
  Delete_Screen,
  Folder_Screen,
  History_Screen,
  Password_Screen,
)
from keyvault.vault import Entry, Vault, Vault_Error

MARK_SYMBOL : str = "●"
MENU_LABEL : str = "MENU"
MENU_ITEMS : tuple[tuple[str, str], ...] = (
  ( "o", "Folder" ),
  ( "space", "Mark" ),
  ( "a", "Mark all" ),
  ( "v", "View" ),
  ( "e", "Encrypt" ),
  ( "d", "Decrypt" ),
  ( "n", "New" ),
  ( "x", "Delete" ),
  ( "h", "History" ),
  ( "l", "Lock" ),
  ( "r", "Refresh" ),
  ( "q", "Quit" ),
)
THEME_NAME : str = "keyvault"
HANDLED_ERRORS : tuple = ( Crypto_Error, Git_Error, Vault_Error, OSError )


def build_menu(
  palette_ : dict[str, str] ,
) -> Text:
  """
  Build the text of the top menu bar.

  Args:
    palette_ (dict[str, str]): Palette from `load_palette`.

  Returns:
    Text: `MENU` label followed by one `key action` pair per command.
  """

  menu : Text = Text()
  menu.append(
    f" {MENU_LABEL} ",
    style=f"bold {palette_[ 'background' ]} on {palette_[ 'cyan' ]}",
  )

  for key, label in MENU_ITEMS:
    menu.append( "  " )
    menu.append( key, style=f"bold {palette_[ 'yellow' ]}" )
    menu.append( f" {label}", style=palette_[ "foreground" ] )

  assert menu.plain.startswith( f" {MENU_LABEL} " ), "menu label missing"

  return menu


def build_theme(
  palette_ : dict[str, str] ,
) -> Theme:
  """
  Convert the color palette to a Textual theme.

  Args:
    palette_ (dict[str, str]): Palette from `load_palette`.

  Returns:
    Theme: Dark theme named `keyvault`.
  """

  assert "background" in palette_, "palette_ lacks a background"

  return Theme(
    name=THEME_NAME,
    primary=palette_[ "blue" ],
    secondary=palette_[ "magenta" ],
    accent=palette_[ "cyan" ],
    success=palette_[ "green" ],
    warning=palette_[ "yellow" ],
    error=palette_[ "red" ],
    foreground=palette_[ "foreground" ],
    background=palette_[ "background" ],
    surface=palette_[ "background" ],
    panel=palette_[ "background" ],
    dark=True,
  )


class Key_Vault_App( App ):
  """Browse encrypt decrypt add and delete secret files."""

  TITLE : str = "KeyVault"
  CSS : str = """
  #menubar {
    height: 1;
    width: 100%;
  }
  #entries {
    height: 1fr;
  }
  #secret-panel {
    height: 1fr;
    border: round $primary;
    border-title-color: $accent;
  }
  """
  BINDINGS : list[Binding] = [
    Binding( "o", "open_folder", "Folder" ),
    Binding( "space", "toggle_mark", "Mark" ),
    Binding( "a", "mark_all", "Mark all" ),
    Binding( "v", "view", "View" ),
    Binding( "e", "encrypt", "Encrypt" ),
    Binding( "d", "decrypt", "Decrypt" ),
    Binding( "n", "new_secret", "New" ),
    Binding( "x", "delete", "Delete" ),
    Binding( "h", "history", "History" ),
    Binding( "l", "lock", "Lock" ),
    Binding( "r", "refresh", "Refresh" ),
    Binding( "q", "quit", "Quit" ),
  ]

  def __init__(
    self ,
    folder_ : Optional[Path] = None ,
    palette_ : Optional[dict[str, str]] = None ,
  ) -> None:
    """
    Args:
      folder_ (Path, optional): Secrets folder. A picker opens when None.
      palette_ (dict, optional): Colors. Loaded from the config when None.
    """

    super().__init__()
    self.palette : dict[str, str] = palette_ or load_palette()
    self.initial_folder : Optional[Path] = folder_
    self.vault : Optional[Vault] = None
    self.password : Optional[str] = None
    self.marked : set[str] = set()
    self.entries : list[Entry] = []

  def compose( self ) -> ComposeResult:
    """Build the main screen: file list on top and secret panel below."""

    yield Header()
    yield Static( build_menu( self.palette ), id="menubar" )
    yield DataTable( cursor_type="row", zebra_stripes=False, id="entries" )
    yield RichLog(
      wrap=True, markup=False, highlight=False, id="secret-panel"
    )
    yield Footer()

  def on_mount( self ) -> None:
    """Apply the theme and open the initial folder."""

    self.register_theme( build_theme( self.palette ) )
    self.theme = THEME_NAME

    table : DataTable = self.query_one( "#entries", DataTable )
    table.add_columns( " ", "Name", "State", "Size", "Modified" )
    table.focus()

    panel : RichLog = self.query_one( "#secret-panel", RichLog )
    panel.border_title = "Decrypted secrets (memory only)"

    if self.initial_folder is not None:
      self.set_folder( self.initial_folder )
    else:
      self.action_open_folder()

  # --------------------------------------------------------------------------
  # State helpers

  def set_folder(
    self ,
    folder_ : Path ,
  ) -> None:
    """Open folder_ as the vault and refresh the view."""

    try:
      self.vault = Vault( folder_ )
    except HANDLED_ERRORS as error:
      self.notify( f"Cannot open {folder_}: {error}", severity="error" )
      return

    self.marked.clear()
    save_last_folder( self.vault.root )
    self.sub_title = str( self.vault.root )

    if self.vault.created_repository:
      self.notify( "Created a local git repository in this folder." )

    self.action_refresh()

  def refresh_table( self ) -> None:
    """Rebuild the file table and keep the cursor on the same file."""

    table : DataTable = self.query_one( "#entries", DataTable )
    previous : Optional[str] = self.cursor_name()

    table.clear()
    self.entries = self.vault.list_entries() if self.vault else []
    self.marked &= { entry.name for entry in self.entries }

    for entry in self.entries:
      color : str = (
        self.palette[ "green" ] if entry.encrypted else self.palette[ "red" ]
      )
      table.add_row(
        Text( MARK_SYMBOL if entry.name in self.marked else " ", style=color ),
        Text( entry.name, style=color ),
        Text( "encrypted" if entry.encrypted else "plaintext", style=color ),
        Text( f"{entry.size} B", style=self.palette[ "muted" ] ),
        Text( entry.modified, style=self.palette[ "muted" ] ),
        key=entry.name,
      )

    names : list[str] = [ entry.name for entry in self.entries ]
    if previous in names:
      table.move_cursor( row=names.index( previous ) )

  def cursor_name( self ) -> Optional[str]:
    """Return the file name under the cursor or None for an empty list."""

    table : DataTable = self.query_one( "#entries", DataTable )

    if table.row_count == 0 or table.cursor_row >= len( self.entries ):
      return None

    return self.entries[ table.cursor_row ].name

  def target_entries( self ) -> list[Entry]:
    """Return marked entries or the entry under the cursor."""

    if len( self.marked ) > 0:
      return [ e for e in self.entries if e.name in self.marked ]

    name : Optional[str] = self.cursor_name()

    return [ e for e in self.entries if e.name == name ]

  def write_panel(
    self ,
    title_ : str ,
    body_ : str ,
    style_ : Optional[str] = None ,
  ) -> None:
    """Append a titled block to the bottom panel."""

    panel : RichLog = self.query_one( "#secret-panel", RichLog )
    panel.write( Text( f"── {title_} ──", style=self.palette[ "cyan" ] ) )
    panel.write( Text( body_, style=style_ or self.palette[ "foreground" ] ) )

  async def request_password(
    self ,
    confirm_ : bool = False ,
  ) -> Optional[str]:
    """
    Return the cached password or ask once and cache the answer.

    Args:
      confirm_ (bool): Ask twice when no password is cached yet.
    """

    if self.password is not None:
      return self.password

    answer : Optional[str] = await self.push_screen_wait(
      Password_Screen( confirm_=confirm_ )
    )

    if answer is not None:
      self.password = answer

    return answer

  def report_error(
    self ,
    error_ : Exception ,
  ) -> None:
    """Notify the user and forget the password after a wrong one."""

    if isinstance( error_, Wrong_Password_Error ):
      self.password = None

    self.notify( str( error_ ), severity="error", timeout=8 )

  # --------------------------------------------------------------------------
  # Actions

  def action_open_folder( self ) -> None:
    """Open the folder picker."""

    start : Path = self.vault.root if self.vault else Path.home()

    def on_chosen( folder_ : Optional[Path] ) -> None:
      if folder_ is not None:
        self.set_folder( folder_ )

    self.push_screen( Folder_Screen( start ), on_chosen )

  def action_refresh( self ) -> None:
    """Reload the folder listing."""

    self.refresh_table()

  def action_toggle_mark( self ) -> None:
    """Mark or unmark the file under the cursor."""

    name : Optional[str] = self.cursor_name()

    if name is None:
      return

    self.marked ^= { name }
    self.refresh_table()

  def action_mark_all( self ) -> None:
    """Mark every file or clear the marks when all are marked."""

    names : set[str] = { entry.name for entry in self.entries }
    self.marked = set() if self.marked == names else names
    self.refresh_table()

  def action_lock( self ) -> None:
    """Forget the cached password and clear the secret panel."""

    self.password = None
    self.query_one( "#secret-panel", RichLog ).clear()
    self.notify( "Password forgotten and panel cleared." )

  def on_data_table_row_selected(
    self ,
    event_ : DataTable.RowSelected ,
  ) -> None:
    """Enter on a row of the file table views the secrets."""

    if event_.data_table.id == "entries":
      self.action_view()

  @work
  async def action_view( self ) -> None:
    """Show the decrypted content of the targets in the bottom panel."""

    targets : list[Entry] = self.target_entries()

    if self.vault is None or len( targets ) == 0:
      return

    password : Optional[str] = ""
    if any( entry.encrypted for entry in targets ):
      password = await self.request_password()
      if password is None:
        return

    panel : RichLog = self.query_one( "#secret-panel", RichLog )
    panel.clear()

    for entry in targets:
      try:
        data : bytes = self.vault.read_secret( entry.name, password )
      except HANDLED_ERRORS as error:
        self.report_error( error )
        if isinstance( error, Wrong_Password_Error ):
          return
        continue
      self.write_panel(
        entry.name, data.decode( errors="replace" )
      )

  @work
  async def action_encrypt( self ) -> None:
    """Encrypt the plaintext targets with one password."""

    targets : list[Entry] = [
      e for e in self.target_entries() if not e.encrypted
    ]

    if self.vault is None or len( targets ) == 0:
      self.notify( "No plaintext file selected." )
      return

    password : Optional[str] = await self.request_password( confirm_=True )
    if password is None:
      return

    for entry in targets:
      try:
        self.vault.encrypt_entry( entry.name, password )
      except HANDLED_ERRORS as error:
        self.report_error( error )

    self.marked.clear()
    self.refresh_table()
    self.notify( f"Encrypted {len( targets )} file(s)." )

  @work
  async def action_decrypt( self ) -> None:
    """Decrypt the encrypted targets to plaintext files on disk."""

    targets : list[Entry] = [
      e for e in self.target_entries() if e.encrypted
    ]

    if self.vault is None or len( targets ) == 0:
      self.notify( "No encrypted file selected." )
      return

    password : Optional[str] = await self.request_password()
    if password is None:
      return

    for entry in targets:
      try:
        self.vault.decrypt_entry( entry.name, password )
      except HANDLED_ERRORS as error:
        self.report_error( error )
        if isinstance( error, Wrong_Password_Error ):
          break

    self.marked.clear()
    self.refresh_table()

  @work
  async def action_new_secret( self ) -> None:
    """Create a new encrypted secret and commit it."""

    if self.vault is None:
      return

    answer : Optional[tuple[str, str]] = await self.push_screen_wait(
      Add_Secret_Screen()
    )
    if answer is None:
      return

    password : Optional[str] = await self.request_password( confirm_=True )
    if password is None:
      return

    try:
      created : str = self.vault.add_secret( answer[ 0 ], answer[ 1 ], password )
    except HANDLED_ERRORS as error:
      self.report_error( error )
      return

    self.refresh_table()
    self.notify( f"Saved and committed {created}." )

  @work
  async def action_delete( self ) -> None:
    """Delete the file under the cursor after name confirmation."""

    name : Optional[str] = self.cursor_name()

    if self.vault is None or name is None:
      return

    typed : Optional[str] = await self.push_screen_wait( Delete_Screen( name ) )
    if typed is None:
      return

    try:
      self.vault.delete_entry( name, typed )
    except HANDLED_ERRORS as error:
      self.report_error( error )
      return

    self.refresh_table()
    self.notify( f"Deleted {name}." )

  @work
  async def action_history( self ) -> None:
    """Show git history of the file and optionally one decrypted version."""

    name : Optional[str] = self.cursor_name()

    if self.vault is None or name is None:
      return

    try:
      revisions : list[Revision] = self.vault.history( name )
    except HANDLED_ERRORS as error:
      self.report_error( error )
      return

    chosen : Optional[Revision] = await self.push_screen_wait(
      History_Screen( name, revisions )
    )
    if chosen is None:
      return

    password : Optional[str] = await self.request_password()
    if password is None:
      return

    try:
      data : bytes = self.vault.read_revision( name, chosen.commit, password )
    except HANDLED_ERRORS as error:
      self.report_error( error )
      return

    panel : RichLog = self.query_one( "#secret-panel", RichLog )
    panel.clear()
    self.write_panel(
      f"{name} @ {chosen.short_commit} {chosen.date}",
      data.decode( errors="replace" ),
    )
