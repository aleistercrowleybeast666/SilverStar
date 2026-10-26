"""Trusted validator for data-only object declarations, shared with SCG."""
from pathlib import Path
import sys

try:
    import silverstar_data_contracts
except ModuleNotFoundError as error:
    if error.name != 'silverstar_data_contracts':
        raise
    # Fixed monorepo location; never import from an opened decoder package.
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'SCG/src'))

from silverstar_data_contracts.objects import ObjectCatalog_Validate

__all__ = ['ObjectCatalog_Validate']
