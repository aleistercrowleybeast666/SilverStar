from __future__ import annotations

from dataclasses import dataclass

from silverstar_flp.core.dataset import TimeSeries


@dataclass(frozen=True, slots=True)
class ChannelDisplayMetadata:
    """Localized presentation metadata kept separate from stable channel IDs."""

    channel_id: str
    title_zh: str
    title_en: str
    quantity_zh: str
    quantity_en: str

    def Title_Get(self, language: str) -> str:
        return self.title_zh if language == "zh_CN" else self.title_en

    def Quantity_Get(self, language: str) -> str:
        return self.quantity_zh if language == "zh_CN" else self.quantity_en


_CHANNEL_METADATA = {
    "navigation.velocity_enu": ChannelDisplayMetadata(
        "navigation.velocity_enu", "飞行速度（ENU）", "Flight Velocity (ENU)", "速度", "Velocity"
    ),
    "navigation.position_enu": ChannelDisplayMetadata(
        "navigation.position_enu", "飞行位置（ENU）", "Flight Position (ENU)", "位置", "Position"
    ),
    "imu.corrected.accel_b": ChannelDisplayMetadata(
        "imu.corrected.accel_b",
        "校正后加速度（机体系）",
        "Corrected Acceleration (Body)",
        "加速度",
        "Acceleration",
    ),
    "imu.corrected.gyro_b": ChannelDisplayMetadata(
        "imu.corrected.gyro_b",
        "校正后角速度（机体系）",
        "Corrected Angular Rate (Body)",
        "角速度",
        "Angular Rate",
    ),
    "attitude.q_nb": ChannelDisplayMetadata(
        "attitude.q_nb",
        "软件姿态四元数（WXYZ，机体 → ENU）",
        "Software Attitude Quaternion (WXYZ, Body to ENU)",
        "四元数",
        "Quaternion",
    ),
    "kf6.covariance.diagonal": ChannelDisplayMetadata(
        "kf6.covariance.diagonal",
        "KF_6 协方差对角线",
        "KF_6 Covariance Diagonal",
        "协方差",
        "Covariance",
    ),
    "kf6.innovation.position": ChannelDisplayMetadata(
        "kf6.innovation.position",
        "KF_6 位置新息",
        "KF_6 Position Innovation",
        "位置新息",
        "Position Innovation",
    ),
    "kf6.innovation.velocity": ChannelDisplayMetadata(
        "kf6.innovation.velocity",
        "KF_6 速度新息",
        "KF_6 Velocity Innovation",
        "速度新息",
        "Velocity Innovation",
    ),
    "kf6.innovation.baro": ChannelDisplayMetadata(
        "kf6.innovation.baro",
        "KF_6 气压高度新息",
        "KF_6 Barometer Innovation",
        "高度新息",
        "Altitude Innovation",
    ),
    "kf6.nis.position": ChannelDisplayMetadata(
        "kf6.nis.position", "KF_6 位置 NIS", "KF_6 Position NIS", "NIS", "NIS"
    ),
    "kf6.nis.velocity": ChannelDisplayMetadata(
        "kf6.nis.velocity", "KF_6 速度 NIS", "KF_6 Velocity NIS", "NIS", "NIS"
    ),
    "kf6.nis.baro": ChannelDisplayMetadata(
        "kf6.nis.baro", "KF_6 气压高度 NIS", "KF_6 Barometer NIS", "NIS", "NIS"
    ),
    "kf6.update_result": ChannelDisplayMetadata(
        "kf6.update_result",
        "KF_6 量测更新结果",
        "KF_6 Measurement Update Results",
        "更新结果",
        "Update Result",
    ),
    "kf6.measurement_r_scale": ChannelDisplayMetadata(
        "kf6.measurement_r_scale",
        "KF_6 量测噪声缩放",
        "KF_6 Measurement-noise Scale",
        "R 缩放",
        "R Scale",
    ),
}

_QUANTITIES = {
    "acceleration": ("加速度", "Acceleration"),
    "angle": ("角度", "Angle"),
    "angular_rate": ("角速度", "Angular Rate"),
    "covariance": ("协方差", "Covariance"),
    "dimension": ("维数", "Dimension"),
    "innovation": ("新息", "Innovation"),
    "nis": ("NIS", "NIS"),
    "position": ("位置", "Position"),
    "quaternion": ("四元数", "Quaternion"),
    "scale": ("缩放", "Scale"),
    "sequence": ("序号", "Sequence"),
    "specific_force": ("比力", "Specific Force"),
    "state": ("状态", "State"),
    "status": ("状态", "Status"),
    "time": ("时间", "Time"),
    "update_result": ("更新结果", "Update Result"),
    "velocity": ("速度", "Velocity"),
    "velocity_increment": ("速度增量", "Velocity Increment"),
}

_COMPONENTS = {
    "GNSS position": ("GNSS 位置", "GNSS Position"),
    "GNSS velocity": ("GNSS 速度", "GNSS Velocity"),
    "Barometer": ("气压高度", "Barometer"),
}


def ChannelCanonicalId_Get(channel_id: str) -> str:
    for canonical_id in sorted(_CHANNEL_METADATA, key=len, reverse=True):
        if channel_id == canonical_id or channel_id.endswith("." + canonical_id):
            return canonical_id
        if channel_id.endswith("/ " + canonical_id):
            return canonical_id
    return channel_id


def ChannelDisplayMetadata_Get(
    channel_id: str,
    series: TimeSeries,
) -> ChannelDisplayMetadata:
    canonical_id = ChannelCanonicalId_Get(channel_id)
    metadata = _CHANNEL_METADATA.get(canonical_id)
    if metadata is not None:
        return metadata
    quantity_zh, quantity_en = _QUANTITIES.get(
        series.quantity,
        (series.quantity, series.quantity),
    )
    return ChannelDisplayMetadata(
        canonical_id,
        f"{quantity_zh}（数据通道）",
        f"{quantity_en} (Data Channel)",
        quantity_zh,
        quantity_en,
    )


def ComponentLabel_Get(label: str, language: str) -> str:
    translated = _COMPONENTS.get(label)
    if translated is None:
        return label
    return translated[0] if language == "zh_CN" else translated[1]
