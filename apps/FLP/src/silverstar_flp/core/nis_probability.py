"""Chi-square configuration conversion; paired apps share contract reference vectors.

No target/sample-path use. Regularized gamma series/continued fraction with
bounded convergence checks, then monotone bisection for inverse CDF.
"""
from __future__ import annotations

import math
from functools import lru_cache

NIS_INPUT_SCHEMA = "silverstar.nis-cdf-input/1.0"


def _Df_Validate(df: int) -> None:
    if type(df) is not int or not 1 <= df <= 256:
        raise ValueError("nis_df_invalid")


def _GammaTails_Get(a: float, x: float) -> tuple[float, float]:
    if x == 0.0:
        return 0.0, 1.0
    factor = math.exp(a * math.log(x) - x - math.lgamma(a))
    if x < a + 1.0:
        term = total = 1.0 / a
        for i in range(1, 4097):
            term *= x / (a + i)
            total += term
            if abs(term) <= abs(total) * 2.0e-15:
                p = min(1.0, max(0.0, factor * total))
                return p, 1.0 - p
    else:
        tiny = 1.0e-300
        b = x + 1.0 - a
        c, d = 1.0 / tiny, 1.0 / b
        total = d
        for i in range(1, 4097):
            an = -i * (i - a)
            b += 2.0
            d = an * d + b
            if abs(d) < tiny:
                d = math.copysign(tiny, d)
            c = b + an / c
            if abs(c) < tiny:
                c = math.copysign(tiny, c)
            d = 1.0 / d
            change = d * c
            total *= change
            if abs(change - 1.0) <= 2.0e-15:
                q = min(1.0, max(0.0, factor * total))
                return 1.0 - q, q
    raise ValueError("nis_gamma_not_converged")


def ChiSquareCdf_Get(threshold: float, df: int) -> float:
    _Df_Validate(df)
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or threshold < 0:
        raise ValueError("nis_threshold_invalid")
    return _GammaTails_Get(df / 2.0, threshold / 2.0)[0]


def ChiSquareQuantile_Get(probability: float, df: int) -> float:
    _Df_Validate(df)
    if (type(probability) not in (int, float) or not math.isfinite(probability)
            or not 0.0 < probability < 1.0):
        raise ValueError("nis_probability_invalid")
    return _ChiSquareQuantile_Get(probability, df)


@lru_cache(maxsize=256, typed=True)
def _ChiSquareQuantile_Get(probability: float, df: int) -> float:
    _Df_Validate(df)
    if (type(probability) not in (int, float) or not math.isfinite(probability)
            or not 0.0 < probability < 1.0):
        raise ValueError("nis_probability_invalid")
    low, high = 0.0, float(max(1, df))
    upper = probability > 0.5
    target = 1.0 - probability if upper else probability
    def below(x: float) -> bool:
        p, q = _GammaTails_Get(df / 2.0, x / 2.0)
        return q > target if upper else p < target
    for _ in range(64):
        if not below(high):
            break
        high *= 2.0
    else:
        raise ValueError("nis_quantile_unbounded")
    for _ in range(1200):
        middle = (low + high) / 2.0
        if middle == low or middle == high:
            return middle
        if below(middle):
            low = middle
        else:
            high = middle
        if low > 0.0 and high - low <= low * 4.0e-15:
            return (low + high) / 2.0
    raise ValueError("nis_quantile_not_converged")


def NisInput_Create(probability: float, df: int) -> dict:
    ChiSquareQuantile_Get(probability, df)
    return {"schema_id": NIS_INPUT_SCHEMA, "unit": "fraction",
            "degrees_of_freedom": df, "probability": probability}


def NisInput_Resolve(value: object, df: int | None = None) -> float:
    if type(value) in (int, float) and math.isfinite(value):
        return value
    if not isinstance(value, dict) or set(value) != {
            "schema_id", "unit", "degrees_of_freedom", "probability"}:
        raise ValueError("nis_input_invalid")
    if value["schema_id"] != NIS_INPUT_SCHEMA or value["unit"] != "fraction":
        raise ValueError("nis_input_schema_or_unit_invalid")
    if df is not None and value["degrees_of_freedom"] != df:
        raise ValueError("nis_input_df_mismatch")
    return ChiSquareQuantile_Get(value["probability"], value["degrees_of_freedom"])


def NisInputs_Validate(inputs: object, actual_values: dict, declared_df: dict[str, int]) -> None:
    import struct
    if not isinstance(inputs, dict):
        raise ValueError("nis_inputs_invalid")
    for name, value in inputs.items():
        if name not in declared_df or not isinstance(value, dict) or name not in actual_values:
            raise ValueError("nis_input_parameter_unknown")
        x = NisInput_Resolve(value, declared_df[name])
        x = struct.unpack("<f", struct.pack("<f", x))[0]
        if not math.isfinite(x) or x != actual_values[name]:
            raise ValueError("nis_input_actual_mismatch")


def RecordedNisDf_Get(declaration: object, parameter_id: str) -> int | None:
    """Unknown or malformed decoder declarations never imply a recorded CDF."""
    from collections.abc import Mapping
    if not isinstance(declaration, Mapping):
        return None
    if (declaration.get("schema_id") != "silverstar.nis-gating/1.0"
            or declaration.get("definition") != "raw_r_transpose_S_inverse_r"
            or declaration.get("probability_unit") != "fraction"):
        return None
    dimensions = declaration.get("threshold_df")
    if not isinstance(dimensions, Mapping):
        return None
    df = dimensions.get(parameter_id)
    return df if type(df) is int and 1 <= df <= 256 else None
