"""Textual application that manages a folder of ccrypt secrets."""

import sys
from pathlib import Path
from typing import Iterable, Optional

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import DataTable, Footer, Header, RichLog, Static

from keyvault import clipboard
from keyvault.config import (
  load_backend,
  load_palette,
  save_backend,
  save_last_folder,
)
from keyvault.crypto import (
  BACKEND_CCRYPT,
  BACKEND_RAGE,
  BACKEND_SUFFIXES,
  Crypto_Error,
  Wrong_Password_Error,
  find_ccrypt,
  find_rage,
)
from keyvault.exports import (
  Export_Error,
  format_export_line,
  validate_variable_name,
  write_env_variable,
)
from keyvault.git_store import Git_Error, Revision
from keyvault.screens import (
  Add_Secret_Screen,
  Delete_Screen,
  Export_Screen,
  Folder_Screen,
  History_Screen,
  Password_Screen,
  Permissions_Screen,
  Rename_Screen,
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
  ( "f2", "Rename" ),
  ( "m", "Permissions" ),
  ( "t", "Export" ),
  ( "b", "Backend" ),
  ( "l", "Lock session" ),
  ( "r", "Refresh" ),
  ( "ctrl+c", "Copy" ),
  ( "ctrl+v", "Paste" ),
  ( "q", "Quit" ),
)
THEME_NAME : str = "keyvault"
HANDLED_ERRORS : tuple = (
  Crypto_Error,
  Git_Error,
  Vault_Error,
  Export_Error,
  OSError,
)
QUIT_DESCRIPTION : str = "Quit the application"


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
    height: auto;
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
    Binding( "f2", "rename", "Rename" ),
    Binding( "m", "permissions", "Permissions" ),
    Binding( "t", "export", "Export" ),
    Binding( "b", "switch_backend", "Backend" ),
    Binding( "l", "lock", "Lock session" ),
    Binding( "r", "refresh", "Refresh" ),
    Binding( "ctrl+c", "copy_panel", "Copy" ),
    Binding( "ctrl+v", "paste_secret", "Paste" ),
    Binding( "q", "quit", "Quit" ),
  ]

  def __init__(
    self ,
    folder_ : Optional[Path] = None ,
    palette_ : Optional[dict[str, str]] = None ,
    backend_ : Optional[str] = None ,
  ) -> None:
    """
    Args:
      folder_ (Path, optional): Secrets folder. A picker opens when None.
      palette_ (dict, optional): Colors. Loaded from the config when None.
      backend_ (str, optional): `ccrypt` or `rage`. The last used backend
        is loaded from the state file when None.
    """

    super().__init__()
    self.backend : str = backend_ or load_backend()
    self.pending_exports : list[str] = []
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
    yield Footer( show_command_palette=False )

  def get_system_commands(
    self ,
    screen : Screen ,
  ) -> Iterable[SystemCommand]:
    """Offer the default palette commands with a shorter Quit help text."""

    for command in super().get_system_commands( screen ):
      if command.title == "Quit":
        yield SystemCommand( "Quit", QUIT_DESCRIPTION, self.action_quit )
      else:
        yield command

  @property
  def clipboard( self ) -> str:
    """System clipboard when readable and the in-app clipboard otherwise."""

    system_text : Optional[str] = clipboard.read_text()

    return system_text if system_text is not None else self._clipboard

  def copy_to_clipboard(
    self ,
    text_ : str ,
  ) -> None:
    """Copy through OSC 52 and through the clipboard tools of the host."""

    super().copy_to_clipboard( text_ )
    clipboard.copy_text( text_ )

  def on_mount( self ) -> None:
    """Apply the theme and open the initial folder."""

    self.register_theme( build_theme( self.palette ) )
    self.theme = THEME_NAME

    table : DataTable = self.query_one( "#entries", DataTable )
    table.add_columns(
      " ", "Name", "State", "Size", "Modified", "Mode", "Owner:Group"
    )
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
      self.vault = Vault( folder_, self.backend )
    except HANDLED_ERRORS as error:
      self.notify( f"Cannot open {folder_}: {error}", severity="error" )
      return

    self.marked.clear()
    save_last_folder( self.vault.root )
    self.update_sub_title()

    if self.vault.created_repository:
      self.notify( "Created a local git repository in this folder." )

    self.action_refresh()

  def update_sub_title( self ) -> None:
    """Show the folder and the active backend in the header."""

    if self.vault is not None:
      self.sub_title = f"{self.vault.root}  [{self.backend}]"

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
        Text( entry.mode, style=self.palette[ "muted" ] ),
        Text( f"{entry.owner}:{entry.group}", style=self.palette[ "muted" ] ),
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
  async def action_new_secret(
    self ,
    initial_secret_ : str = "" ,
  ) -> None:
    """Create a new encrypted secret and commit it."""

    if self.vault is None:
      return

    answer : Optional[tuple[str, str]] = await self.push_screen_wait(
      Add_Secret_Screen(
        secret_=initial_secret_, suffix_=BACKEND_SUFFIXES[ self.backend ]
      )
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
  async def action_rename( self ) -> None:
    """Rename the file under the cursor."""

    name : Optional[str] = self.cursor_name()

    if self.vault is None or name is None:
      return

    encrypted : bool = any( e.encrypted for e in self.entries if e.name == name )
    typed : Optional[str] = await self.push_screen_wait(
      Rename_Screen( name, encrypted_=encrypted )
    )
    if typed is None:
      return

    try:
      new_name : str = self.vault.rename_entry( name, typed )
    except HANDLED_ERRORS as error:
      self.report_error( error )
      return

    self.marked.discard( name )
    self.refresh_table()
    self.query_one( "#entries", DataTable ).move_cursor(
      row=[ e.name for e in self.entries ].index( new_name )
    )
    self.notify( f"Renamed {name} to {new_name}." )

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

  # --------------------------------------------------------------------------
  # Clipboard, backend, permissions and export

  def panel_text( self ) -> str:
    """Return the text currently shown in the secret panel."""

    panel : RichLog = self.query_one( "#secret-panel", RichLog )

    return "\n".join(
      "".join( segment.text for segment in strip ).rstrip()
      for strip in panel.lines
    )

  def action_copy_panel( self ) -> None:
    """Copy the secret panel to the clipboard."""

    text : str = self.panel_text().strip()

    if text == "":
      self.notify( "The secret panel is empty." )
      return

    self.copy_to_clipboard( text )
    self.notify( "Copied the secret panel to the clipboard." )

  def action_paste_secret( self ) -> None:
    """Open the new secret dialog with the clipboard as secret text."""

    text : str = self.clipboard

    if text == "":
      self.notify( "The clipboard is empty." )
      return

    self.action_new_secret( text )

  def action_switch_backend( self ) -> None:
    """Toggle between ccrypt and rage for new ciphertext."""

    target : str = (
      BACKEND_RAGE if self.backend == BACKEND_CCRYPT else BACKEND_CCRYPT
    )

    try:
      find_rage() if target == BACKEND_RAGE else find_ccrypt()
    except Crypto_Error as error:
      self.notify( str( error ), severity="error", timeout=8 )
      return

    self.backend = target
    save_backend( target )

    if self.vault is not None:
      self.vault.backend = target
    self.update_sub_title()
    self.notify(
      f"New files use {target} ({BACKEND_SUFFIXES[ target ]})."
      " Existing files keep their own format."
    )

  @work
  async def action_permissions( self ) -> None:
    """Change mode and owner and group of the targets."""

    targets : list[Entry] = self.target_entries()

    if self.vault is None or len( targets ) == 0:
      return

    first : Entry = targets[ 0 ]
    answer : Optional[tuple[str, str, str]] = await self.push_screen_wait(
      Permissions_Screen(
        [ entry.name for entry in targets ],
        mode_=self.vault.octal_mode( first.name ),
        owner_=first.owner,
        group_=first.group,
      )
    )
    if answer is None:
      return

    changed : int = 0
    for entry in targets:
      try:
        self.vault.set_permissions( entry.name, *answer )
        changed += 1
      except HANDLED_ERRORS as error:
        self.report_error( error )

    self.refresh_table()
    if changed > 0:
      self.notify( f"Changed permissions of {changed} file(s)." )

  @work
  async def action_export( self ) -> None:
    """Export the decrypted secret under the cursor as `.env` or `export`."""

    name : Optional[str] = self.cursor_name()

    if self.vault is None or name is None:
      return

    answer : Optional[tuple[str, str]] = await self.push_screen_wait(
      Export_Screen( name )
    )
    if answer is None:
      return

    variable, kind = answer
    try:
      validate_variable_name( variable )
    except HANDLED_ERRORS as error:
      self.report_error( error )
      return

    password : Optional[str] = ""
    if any( e.encrypted for e in self.entries if e.name == name ):
      password = await self.request_password()
      if password is None:
        return

    try:
      secret : str = self.vault.read_secret( name, password ).decode(
        errors="replace"
      ).rstrip( "\n" )
      if kind == Export_Screen.FORMAT_ENV:
        target : Path = write_env_variable( Path.cwd(), variable, secret )
        self.notify( f"Wrote {variable} to {target} (mode 600)." )
      else:
        self.export_to_shell( format_export_line( variable, secret ) )
    except HANDLED_ERRORS as error:
      self.report_error( error )

  def export_to_shell(
    self ,
    line_ : str ,
  ) -> None:
    """
    Hand an `export` line to the calling shell.

    A child process cannot change the environment of its parent. When
    stdout is captured with `eval "$(keyvault)"` the line is printed at exit.
    Otherwise the line goes to the clipboard.
    """

    assert line_.startswith( "export " ), "line_ must be an export command"

    if sys.__stdout__ is not None and not sys.__stdout__.isatty():
      self.pending_exports.append( line_ )
      self.notify( "The export command runs in your shell when KeyVault quits." )
      return

    self.copy_to_clipboard( line_ )
    self.notify(
      "Copied the export command. Start KeyVault with"
      " eval \"$(keyvault)\" to apply it automatically.",
      timeout=10,
    )
