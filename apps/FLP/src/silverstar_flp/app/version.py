"""Authoritative SilverStar_FLP product identity and application version."""

from pathlib import Path

PRODUCT_NAME = "SilverStar FLP"
__version__ = (Path(__file__).resolve().parents[5] / "VERSION").read_text(encoding="ascii").strip()

__all__ = ["PRODUCT_NAME", "__version__"]
