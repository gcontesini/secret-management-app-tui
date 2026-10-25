# Install git and uv on Windows with winget. ccrypt has no winget package.
# Download the ccrypt Windows build from https://ccrypt.sourceforge.net
# and place ccrypt.exe in a folder on PATH.
$ErrorActionPreference = "Stop"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  winget install --id Git.Git -e --source winget
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  winget install --id astral-sh.uv -e --source winget
}
if (-not (Get-Command ccrypt -ErrorAction SilentlyContinue)) {
  Write-Warning "ccrypt.exe is not on PATH. Install it manually."
}
