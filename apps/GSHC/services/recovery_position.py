"""Display-only last received telemetry position; no extrapolation or control."""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math
from pathlib import Path


class RecoveryObserveResult(str, Enum):
    Accepted = "accepted"
    Invalid = "invalid"
    Older = "older"


@dataclass(frozen=True)
class RecoverySample:
    session: int
    time_ms: int
    enu_m: tuple[float, float, float]
    received_ns: int
    source: str
    sequence: int


@dataclass(frozen=True)
class AbsoluteRecoverySample:
    session: int
    sequence: int
    latitude_e7: int
    longitude_e7: int
    height_mm: int | None
    age_s: float | None
    accuracy_cm: int
    flags: int
    satellites: int
    received_ns: int
    source: str


class RecoveryPosition:
    def __init__(self):
        self.sample = None
        self.confirmed_session = None
        self.absolute = None

    def Position_Observe(self, session, time_ms, position, received_ns, *, source, sequence=0):
        if (type(session) is not int or session < 0 or type(time_ms) is not int
                or time_ms < 0 or type(received_ns) is not int or received_ns < 0
                or type(sequence) is not int or not 0 <= sequence <= 255
                or type(source) is not str or not 1 <= len(source) <= 512):
            return RecoveryObserveResult.Invalid
        try:
            if len(position) != 3 or any(type(v) is bool for v in position):
                return RecoveryObserveResult.Invalid
            point = tuple(float(v) for v in position)
        except (TypeError, ValueError, OverflowError):
            return RecoveryObserveResult.Invalid
        if not all(math.isfinite(v) for v in point) or not math.isfinite(math.hypot(*point[:2])):
            return RecoveryObserveResult.Invalid
        old = self.sample
        if old is not None and (session < old.session or
                (session == old.session and (time_ms < old.time_ms or received_ns < old.received_ns))):
            return RecoveryObserveResult.Older
        if old is None or old.session != session:
            self.confirmed_session = None
        self.sample = RecoverySample(session, time_ms, point, received_ns, source, sequence)
        return RecoveryObserveResult.Accepted

    def Absolute_Observe(self, frame, received_ns, *, source):
        if frame.message_type != 0x18 or type(received_ns) is not int or received_ns < 0:
            return RecoveryObserveResult.Invalid
        fields = frame.values
        if not fields['position_flags'] & 1:
            return RecoveryObserveResult.Invalid
        old = self.absolute
        same_session = old is not None and old.session == frame.boot_session
        if same_session:
            delta = (frame.sequence - old.sequence) & 0xFFFF
            if delta == 0 or delta >= 0x8000 or received_ns < old.received_ns:
                return RecoveryObserveResult.Older
        age = None if fields['sample_age_ms'] == 0xFFFFFFFF else fields['sample_age_ms'] / 1000
        same_point = same_session and (old.latitude_e7, old.longitude_e7) == (fields['latitude_e7'], fields['longitude_e7'])
        if same_point and fields['position_flags'] & 16 and old.age_s is not None:
            elapsed_age = old.age_s + (received_ns - old.received_ns) / 1e9
            age = elapsed_age if age is None else max(age, elapsed_age)
        self.absolute = AbsoluteRecoverySample(frame.boot_session, frame.sequence,
            fields['latitude_e7'], fields['longitude_e7'],
            fields['ellipsoid_height_mm'] if fields['position_flags'] & 2 else None,
            age, fields['horizontal_accuracy_cm'], fields['position_flags'], fields['satellite_count'],
            received_ns, source)
        return RecoveryObserveResult.Accepted

    def Frame_Confirm(self, confirmed):
        self.confirmed_session = self.sample.session if confirmed and self.sample else None

    def Snapshot_Get(self, now_ns, *, connected=False, current_session=None):
        absolute = self.absolute
        if absolute is not None:
            elapsed = max(0, now_ns - absolute.received_ns) / 1e9
            latitude, longitude = absolute.latitude_e7 / 1e7, absolute.longitude_e7 / 1e7
            return {"kind": "wgs84", "sample": absolute, "latitude": latitude, "longitude": longitude,
                "age_s": None if absolute.age_s is None else absolute.age_s + elapsed,
                "receive_age_s": elapsed, "frame_confirmed": False,
                "source_current": bool(connected and current_session == absolute.session),
                "map_url": f"https://www.openstreetmap.org/?mlat={latitude:.7f}&mlon={longitude:.7f}#map=17/{latitude:.7f}/{longitude:.7f}"}
        sample = self.sample
        if sample is None:
            return None
        e, n, u = sample.enu_m
        radius = math.hypot(e, n)
        confirmed = self.confirmed_session == sample.session
        return {
            "sample": sample, "e_m": e, "n_m": n, "u_m": u,
            "horizontal_m": radius,
            "bearing_deg": (math.degrees(math.atan2(e, n)) % 360.0) if confirmed and radius > 0 else None,
            "frame_confirmed": confirmed,
            "age_s": (now_ns - sample.received_ns) / 1e9 if now_ns >= sample.received_ns else None,
            "source_current": bool(connected and current_session == sample.session),
        }


def Recovery_Text(snapshot):
    if snapshot is None:
        return "落地寻回 / Recovery\n尚无有效实收遥测位置 / No valid received position."
    sample = snapshot["sample"]
    if snapshot.get("kind") == "wgs84":
        age_text = "未知" if snapshot['age_s'] is None else f"{snapshot['age_s']:.1f} s"
        accuracy = "未知" if sample.accuracy_cm == 65535 else (">=655.34 m" if sample.accuracy_cm == 65534 else f"{sample.accuracy_cm / 100:.2f} m")
        height = "未知" if sample.height_mm is None else f"{sample.height_mm / 1000:.3f} m (WGS84 椭球高)"
        return ("最后有效 GNSS 观测 / WGS84\n"
            f"纬度 {snapshot['latitude']:.7f}  经度 {snapshot['longitude']:.7f}\n"
            f"定位年龄 {age_text}；最近定位收包 {snapshot['receive_age_s']:.1f} s 前\n"
            f"水平精度参考 {accuracy}；高度 {height}\n"
            f"来源 {sample.source}；{'保留点' if sample.flags & 16 else '当前定位样本'}；"
            f"{'当前连接' if snapshot['source_current'] else '保留 / 断线或先前会话'}\n"
            f"boot_session={sample.session:08X}；帧序号={sample.sequence}\n"
            "ENU 为辅助相对轨迹；本坐标不代表已确认的实际落点。\n" + snapshot['map_url'])
    age = "unknown" if snapshot["age_s"] is None else f'{snapshot["age_s"]:.1f} s'
    bearing = "未知 / UNKNOWN" if snapshot["bearing_deg"] is None else f'{snapshot["bearing_deg"]:.1f} deg'
    return (
        "落地寻回 / Recovery — 最后观测位置，非实际落点 / last observation, not a landing location\n"
        "原点约定为发射点；未确认原点和初始对向时，仅展示原始遥测坐标。\n"
        "Expected origin: launch point. Before origin/orientation confirmation these are raw received coordinates.\n"
        f'直角 / Cartesian: E={snapshot["e_m"]:.3f} m, N={snapshot["n_m"]:.3f} m, U={snapshot["u_m"]:.3f} m\n'
        f'柱坐标 / Cylindrical: horizontal={snapshot["horizontal_m"]:.3f} m, bearing={bearing}, height={snapshot["u_m"]:.3f} m\n'
        f'方向 / Frame: {"已人工确认 / user confirmed" if snapshot["frame_confirmed"] else "未确认，方位不可用 / unconfirmed, bearing unavailable"}\n'
        "方位定义：真北=0 deg，顺时针；ENU yaw=0 指机体 +X 水平投影朝东。\n"
        "Bearing: true north=0 deg, clockwise; ENU yaw=0 means body +X horizontal projection east.\n"
        f'Telemetry time={sample.time_ms} ms; receive monotonic={sample.received_ns} ns; age since receipt={age}\n'
        f'Source={sample.source}; local session={sample.session}; sequence={sample.sequence}\n'
        f'Status={"current connection" if snapshot["source_current"] else "retained / disconnected or previous session"}; finite received sample; no wire position-valid flag\n'
        "距离和方位从发射点计算，不是从手持设备计算；直线方向不是安全通行路线。\n"
        "Distance/bearing are from launch, not the operator; straight-line direction is not a safe walking route."
    )


def Recovery_Export(path, snapshot, *, exported_at=None):
    if snapshot is None:
        raise ValueError("recovery_position_missing")
    stamp = exported_at or datetime.now(timezone.utc).isoformat()
    text = Recovery_Text(snapshot) + f"\nExport UTC={stamp}\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    return text
