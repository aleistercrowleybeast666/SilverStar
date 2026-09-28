"""Advisory sensor metadata, never part of an algorithm's legal value domain."""
from __future__ import annotations

import math
from typing import Any


def SensorRecommendations_Parse(value: Any) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("metadata.sensor_recommendations must be an array")
    result = []
    required = {"parameter_id", "value", "unit", "representation", "source", "description"}
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != required:
            raise ValueError("sensor recommendation fields are invalid")
        if any(not isinstance(entry[key], str) or not entry[key].strip()
               for key in ("parameter_id", "unit", "representation", "source")):
            raise ValueError("sensor recommendation identity/units are invalid")
        number = entry["value"]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise ValueError("sensor recommendation value must be finite")
        descriptions = entry["description"]
        if not isinstance(descriptions, dict) or not descriptions or any(
            not isinstance(key, str) or not isinstance(text, str) or not text.strip()
            for key, text in descriptions.items()
        ):
            raise ValueError("sensor recommendation description must be localized text")
        result.append(dict(entry))
    return tuple(result)
