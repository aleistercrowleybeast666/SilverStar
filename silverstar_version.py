"""Root release identity for packaging and suite tooling."""

from pathlib import Path

__version__ = (Path(__file__).resolve().parent / "VERSION").read_text(encoding="ascii").strip()
