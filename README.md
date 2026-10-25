# KeyVault

KeyVault is a terminal application that manages secrets stored as `ccrypt` encrypted text files. A local git repository versions the encrypted files. The repository never has a remote.

## Contents

1. [What it does](#what-it-does)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Usage](#usage)
5. [Key bindings](#key-bindings)
6. [Behaviour of each operation](#behaviour-of-each-operation)
7. [Colors](#colors)
8. [Standalone build](#standalone-build)
9. [Development](#development)
10. [Security notes](#security-notes)
11. [Project layout](#project-layout)

## What it does

- Lists the files of one folder of secrets including hidden files.
- Shows a `MENU` bar at the top with every key command.
- Stores every secret as a hidden file. The file name starts with a dot.
- Shows encrypted files in green and plaintext files in red.
- Encrypts and decrypts files with `ccrypt`.
- Asks for the password once per session when several files are processed.
- Prints decrypted secrets in the bottom panel. Nothing is written to disk for this.
- Creates new secrets from typed text. The text is encrypted before it reaches the disk.
- Commits every new encrypted file with the file name as commit message.
- Shows the git history of a file and displays any older version decrypted.
- Deletes a file only after the user types the exact file name.

## Requirements

| Tool | Version | Purpose |
| --- | --- | --- |
| Python | 3.12 | Runtime. Python has no formal LTS label. Version 3.12 receives security fixes until October 2028. |
| uv | 0.11 or newer | Environment and dependency management |
| git | 2.x | Local version history |
| ccrypt | 1.11 | Encryption |
| just | 1.x | Optional. Runs the recipes in `Justfile`. |

## Installation

Install `just` first. See <https://github.com/casey/just>. Then run:

```bash
just install
```

The recipe runs three steps:

1. `ensure-uv` installs uv with the official script when uv is missing.
2. `install-system-deps` installs `git` and `ccrypt` with apt or dnf or pacman or zypper or Homebrew. The script asks for `sudo` when needed.
3. `uv sync` creates `.venv` and installs the locked dependencies.

Without `just` run the commands by hand:

```bash
bash scripts/install_system_deps.sh
uv sync --python 3.12
uv run keyvault
```

On Windows run `scripts/install_system_deps.ps1`. It installs git and uv with winget. The `ccrypt.exe` build must be downloaded from <https://ccrypt.sourceforge.net> and placed in a folder on `PATH`.

## Usage

```bash
just run                 # open the last used folder or ask for one
just run ~/secrets       # open a given folder
uv run keyvault --help
```

When the chosen folder is not a git repository KeyVault runs `git init` in it. KeyVault also writes a `.gitignore` that excludes everything except `*.cpt` files. Plaintext files never enter the repository.

The folder listing is not recursive. Sub folders are not listed. Hidden files are listed. `.git` and `.gitignore` are not listed.

## Key bindings

| Key | Action |
| --- | --- |
| `o` | Open the folder picker |
| `Up` `Down` | Move the cursor |
| `Space` | Mark or unmark the file under the cursor |
| `a` | Mark all files or clear all marks |
| `Enter` or `v` | Print the decrypted content of the marked files in the bottom panel. Without marks the file under the cursor is used. |
| `e` | Encrypt the marked plaintext files |
| `d` | Decrypt the marked encrypted files to plaintext files |
| `n` | Create a new secret. `Ctrl+S` saves the dialog. |
| `x` | Delete the file under the cursor |
| `h` | Show the version history of the file under the cursor |
| `l` | Forget the cached password and clear the bottom panel |
| `r` | Reload the file list |
| `q` | Quit |

## Behaviour of each operation

**Password handling.** The first operation that needs a password opens a dialog. The password stays in memory for the session. `l` removes it. A wrong password is removed from memory automatically. Dialogs that create ciphertext ask for the password twice.

**View.** The file is decrypted in memory and written to the bottom panel. No plaintext file is created.

**Hidden names.** Every secret is a hidden file. A new secret called `bank` is stored as `.bank.cpt`. Encrypting `note.txt` creates `.note.txt.cpt`.

**Encrypt.** `name` becomes `.name.cpt`. The plaintext file is removed. The `.cpt` file is committed with its file name as message.

**Decrypt.** `.name.cpt` becomes `.name`. The plaintext file stays hidden. The `.cpt` file is removed from the working folder. The plaintext file is not committed. Encrypting it again creates a new version in the history.

**New secret.** The typed text is encrypted through a pipe. The result is saved as `.<name>.cpt` and committed with the file name as message. Existing files are never overwritten.

**Delete.** A dialog requires the exact file name. The Delete button stays disabled until the typed text matches. Deleting a tracked file creates a commit named `delete <file>`. The earlier versions remain in the git history.

**History.** The list shows commit hash and date and message of every commit that touched `.<name>.cpt`. `Enter` on a row decrypts that version into the bottom panel. The password of the old version can differ from the current password.

## Colors

- Encrypted files use the `green` color.
- Plaintext files use the `red` color.

The default palette is defined in `src/keyvault/config.py`. The palette can be replaced with the colors of the terminal. Create `~/.config/keyvault/palette.toml` with any of these keys:

```toml
background = "#1e1e2e"
foreground = "#cdd6f4"
muted = "#6c7086"
red = "#f38ba8"
green = "#a6e3a1"
yellow = "#f9e2af"
blue = "#89b4fa"
magenta = "#cba6f7"
cyan = "#94e2d5"
```

Only `#rrggbb` values are accepted. Other values are ignored.

## Standalone build

```bash
just build           # host system
just build-linux     # run on Linux
just build-windows   # run on Windows
```

The result is `dist/keyvault-linux` or `dist/keyvault-windows.exe`. PyInstaller does not cross compile. The Windows executable must be built on Windows. The Windows build has not been tested by the author. The build bundles the `ccrypt` binary found on `PATH`. `git` must be installed on the target machine.

## Development

```bash
just test         # pytest
just test-cov     # pytest with coverage
just lint         # ruff
just export-requirements   # refresh requirements.txt from uv.lock
```

The tests call the real `ccrypt` and `git` programs. The TUI tests use the Textual pilot.

## Security notes

- The password reaches `ccrypt` through an environment variable of the child process. It is not part of the command line.
- Python strings cannot be wiped from memory. The password stays in process memory until the process ends.
- The bottom panel keeps decrypted text in memory. Press `l` to clear it.
- Removed plaintext files are unlinked and not overwritten. Journaling file systems and SSD wear leveling can keep copies of the data.
- Deleting a file does not remove its history. The encrypted versions stay in `.git`.
- `ccrypt` uses Rijndael with a 256 bit block size. Password strength limits the security of every secret.

## Project layout

```text
src/keyvault/
  app.py         main Textual application
  screens.py     dialogs for password and new secret and delete and history and folder
  vault.py       folder operations
  git_store.py   local git operations
  crypto.py      ccrypt wrapper
  config.py      palette and last folder
  cli.py         command line entry point
scripts/         install and build scripts
tests/           pytest suite
Justfile         recipes
```
