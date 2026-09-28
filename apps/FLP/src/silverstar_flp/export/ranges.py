"""Shared deterministic output range and directory planning."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from silverstar_flp.core.time_range import TimePages_Get


def ExportPages_Get(duration, mode="30", custom_duration=30.0, current=None):
    if mode == "Current View":
        start, end = current if current is not None else (0.0, min(30.0, duration))
        return ((min(start, duration), min(end, duration)),)
    if mode == "Full":
        return ((0.0, duration),)
    return TimePages_Get(duration, custom_duration if mode == "Custom" else float(mode))


def GifMetadata_Get(start: float, end: float) -> dict:
    import math
    duration = max(0.0, end - start)
    playback = min(30.0, duration)
    return {
        "source_start_s": start,
        "source_end_s": end,
        "source_duration_s": duration,
        "playback_duration_s": playback,
        "speed_factor": duration / playback if playback else 1.0,
        "fps": 30,
        "motion_frame_count": max(1, math.ceil(playback * 30)),
        "final_hold_frames": 30,
        "final_hold_duration_s": 1.0,
    }


@dataclass(frozen=True)
class PlotDirectory:
    root: Path
    start: float
    end: float

    def __truediv__(self, filename: str) -> Path:
        categories = (("NIS", "NIS"), ("Innovation", "Innovation"),
                      ("Std", "Covariance"), ("Velocity", "Velocity"),
                      ("Position", "Position"), ("Attitude", "Attitude"),
                      ("Acceleration", "IMU"), ("Angular_Rate", "IMU"),
                      ("Landing", "Landing"), ("GNSS", "GNSS"))
        category = next(
            (value for key, value in categories if key.lower() in filename.lower()), "Estimation"
        )
        stem = Path(filename).stem
        # Milliseconds distinguish fractional custom windows without collisions.
        interval = f"{self.start:010.3f}-{self.end:010.3f}"
        return self.root / category / f"{stem}_{interval}.png"
