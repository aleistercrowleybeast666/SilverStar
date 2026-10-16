"""Packaged, trusted snapshots of repository-owned machine-readable contracts.

These files ship with the application; they are not loaded from an opened log,
decoder package, current directory or a neighbouring source checkout.
"""

import json
from importlib.resources import files


def Contract_Load(name: str) -> dict:
    if name not in (
        "navigation_v1.json",
        "navigation_fusion_timing_records_v2.json",
        "navigation_fusion_horizon_records_v1.json",
        "navigation_gnss_reacquisition_v1.json",
    ):
        raise ValueError("unsupported_trusted_contract")
    resource = files("silverstar_flp").joinpath("decoder_profiles", "contracts", name)
    return json.loads(resource.read_text(encoding="utf-8"))
