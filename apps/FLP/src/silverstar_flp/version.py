"""Backward-compatible access to the authoritative application version."""

from silverstar_flp.app.version import PRODUCT_NAME, __version__

__all__ = ["PRODUCT_NAME", "__version__"]
