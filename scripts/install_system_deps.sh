#!/usr/bin/env bash
# Install git and ccrypt with the package manager of the host system.
# Usage: scripts/install_system_deps.sh
set -euo pipefail

PACKAGES=(git ccrypt)

have_all() {
  for tool in git ccrypt; do
    command -v "$tool" >/dev/null 2>&1 || return 1
  done
}

if have_all; then
  echo "git and ccrypt are already installed."
  exit 0
fi

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || {
    echo "Run as root or install sudo." >&2
    exit 1
  }
  SUDO="sudo"
fi

if [ "$(uname -s)" = "Darwin" ]; then
  command -v brew >/dev/null 2>&1 || {
    echo "Install Homebrew first: https://brew.sh" >&2
    exit 1
  }
  brew install "${PACKAGES[@]}"
elif command -v apt-get >/dev/null 2>&1; then
  $SUDO apt-get update
  $SUDO apt-get install -y "${PACKAGES[@]}"
elif command -v dnf >/dev/null 2>&1; then
  $SUDO dnf install -y "${PACKAGES[@]}"
elif command -v pacman >/dev/null 2>&1; then
  $SUDO pacman -S --needed --noconfirm git ccrypt
elif command -v zypper >/dev/null 2>&1; then
  $SUDO zypper install -y "${PACKAGES[@]}"
else
  echo "No supported package manager found. Install git and ccrypt manually." >&2
  exit 1
fi

have_all && echo "Installed git and ccrypt." || {
  echo "Installation finished but git or ccrypt is still missing." >&2
  exit 1
}
