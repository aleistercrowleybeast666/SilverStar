"""GUI-owned, bounded raw task positions; separate from ten-second curve history."""

import math
from collections import deque
from enum import Enum

from config import HORIZONTAL_TRAJECTORY_MAX_POINTS


class MissionTrajectoryAppendResult(Enum):
    ADDED = "ADDED"
    INVALID_INPUT = "INVALID_INPUT"
    OUT_OF_ORDER = "OUT_OF_ORDER"


class MissionTrajectoryHistory:
    def __init__(self, max_points=HORIZONTAL_TRAJECTORY_MAX_POINTS):
        if type(max_points) is not int or max_points < 2:
            raise ValueError("mission_trajectory_capacity_invalid")
        self.max_points = max_points
        self._samples = deque(maxlen=max_points)
        self.revision = 0
        self.dropped_sample_count = 0
        self.invalid_sample_count = 0
        self.ignored_non_monotonic_samples = 0
        self.deploy_time_s = None
        self._pending_break = False

    def Sample_Append(self, time_s, position):
        """O(1) append on Controller's GUI mailbox owner, never on serial workers.

        Nonfinite positions stay as gap evidence. Old time is rejected and splits
        the next accepted edge; duplicate time stays and the shared builder splits it.
        Capacity clips oldest original samples, with no sampling or interpolation.
        """
        stamp = float(time_s)
        point = tuple(float(value) for value in position)
        if len(point) != 3 or not math.isfinite(stamp) or stamp < 0:
            self.invalid_sample_count += 1
            self._pending_break = True
            return MissionTrajectoryAppendResult.INVALID_INPUT
        if self._samples and stamp < self._samples[-1][0]:
            self.ignored_non_monotonic_samples += 1
            self._pending_break = True
            return MissionTrajectoryAppendResult.OUT_OF_ORDER
        if len(self._samples) == self.max_points:
            self.dropped_sample_count += 1
        self._samples.append((stamp, point, self._pending_break))
        self._pending_break = False
        self.revision += 1
        return MissionTrajectoryAppendResult.ADDED

    def Deploy_Observe(self, time_s):
        stamp = float(time_s)
        if not math.isfinite(stamp) or stamp < 0:
            raise ValueError("mission_trajectory_deploy_time_invalid")
        if self.deploy_time_s is None:
            # This event outlives the bounded ordinary status/event list.
            self.deploy_time_s = stamp
            self.revision += 1

    def Clear(self):
        self._samples.clear()
        self.dropped_sample_count = 0
        self.invalid_sample_count = 0
        self.ignored_non_monotonic_samples = 0
        self.deploy_time_s = None
        self._pending_break = False
        self.revision += 1

    def Snapshot_Get(self):
        return (
            [item[0] for item in self._samples],
            [item[1] for item in self._samples],
            tuple(item[0] for item in self._samples if item[2]),
        )
