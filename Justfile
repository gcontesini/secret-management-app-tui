# Justfile for KeyVault

venv_dir := ".venv"
python_version := "3.12"

# List the available recipes
default:
  @just --list

# List the available recipes
help:
  @just --list

# Install git and ccrypt with the system package manager
install-system-deps:
  @bash scripts/install_system_deps.sh

# Install uv with the official standalone script when missing
ensure-uv:
  @if ! command -v uv >/dev/null 2>&1; then \
    echo "Installing uv..."; \
    curl -LsSf https://astral.sh/uv/install.sh | sh; \
  else \
    echo "uv is already installed."; \
  fi

# Install system tools and Python dependencies
install: ensure-uv install-system-deps
  @uv sync --python {{python_version}}
  @echo "KeyVault is ready. Start it with: just run"

# Install the Python dependencies only
sync: ensure-uv
  @uv sync --python {{python_version}}

# Start the TUI (Usage: just run [folder])
run *args:
  @uv run keyvault {{args}}

# Run the test suite
test:
  @uv run pytest -q

# Run the test suite with a coverage report
test-cov:
  @uv run pytest --cov=keyvault --cov-report=term-missing -q

# Lint the code with ruff
lint:
  @uv run ruff check src tests scripts

# Export the locked dependencies to requirements.txt
export-requirements:
  @uv export --no-dev --no-hashes --no-emit-project -o requirements.txt

# Build a standalone executable for the host system
build:
  @uv run python scripts/build.py

# Build the standalone Linux executable (run on Linux)
build-linux:
  @uv run python scripts/build.py --target linux

# Build the standalone Windows executable (run on Windows)
build-windows:
  @uv run python scripts/build.py --target windows

# Remove build outputs and caches
clean:
  @rm -rf build dist .pytest_cache .ruff_cache .coverage
  @find . -name "__pycache__" -type d -not -path "./.venv/*" -prune -exec rm -rf {} +
