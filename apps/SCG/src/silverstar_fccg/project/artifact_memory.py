from __future__ import annotations

import re


def ArtifactMemoryMarginLevel_Get(remaining: int, capacity: int) -> str:
    if capacity <= 0 or remaining < 0 or remaining > capacity:
        raise ValueError("Invalid memory region")
    return "error" if remaining * 100 < capacity * 10 else "warning" if remaining * 100 <= capacity * 20 else "success"


def ArtifactMemorySummary_Encode(output: str) -> str:
    values = []
    for name in ("FLASH", "main SRAM", "CCMRAM"):
        matches = re.findall(re.escape(name) + r"\s+used=(\d+)\s+remaining=(\d+)\s+capacity=(\d+)", output)
        if len(matches) != 1:
            return ""
        used, remaining, capacity = map(int, matches[0])
        if capacity <= 0 or remaining != max(0, capacity - used):
            return ""
        values.extend((used, remaining, capacity))
    return "artifact_memory=" + "/".join(map(str, values))


def ArtifactMemorySummary_Decode(summary: str) -> tuple[tuple[int, int, int], ...]:
    if re.fullmatch(r"artifact_memory=\d+(?:/\d+){8}", summary) is None:
        return ()
    values = tuple(map(int, summary.partition("=")[2].split("/")))
    regions = tuple(values[i:i+3] for i in (0, 3, 6))
    if any(capacity <= 0 or remaining != max(0, capacity-used)
           for used, remaining, capacity in regions):
        return ()
    return regions
