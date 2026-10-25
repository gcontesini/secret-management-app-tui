"""KeyVault: terminal manager for ccrypt encrypted secret files."""

__version__ : str = "0.1.0"


def main() -> None:
  """Console entry point declared in pyproject.toml."""

  from keyvault.cli import run

  run()
