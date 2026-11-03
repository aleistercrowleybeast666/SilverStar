"""Admission for the one experimental magnetometer/IMU provider pair."""
from silverstar_fccg.project.compact_logging import CompactLogStreams_Get
from silverstar_fccg.project.model import ProjectModel
from silverstar_fccg.plugins.catalog import PluginCatalog


def MagRotationConfiguration_Validate(model: ProjectModel, catalog: PluginCatalog) -> None:
    view = catalog.ProjectView_Get(model)
    imu = [item for item in model.device_instances if "device.imu" in view.InstanceComponent_Get(item).provides]
    mag = [item for item in model.device_instances if "device.magnetometer" in view.InstanceComponent_Get(item).provides]
    if (len(imu) != 1 or imu[0].plugin != "silverstar.device.imu.bmi088" or
            imu[0].interface not in ("i2c", "spi") or imu[0].profile != "bosch_sync_400_hz"):
        raise ValueError("Mag rotation requires exactly one BMI088 synchronized 400 Hz IMU with both DRDY nets")
    if len(mag) != 1 or mag[0].plugin != "silverstar.device.magnetometer.mmc5983ma":
        raise ValueError("Mag rotation requires exactly one MMC5983MA magnetic endpoint")
    if not model.protocols.get("logging") or not model.protocols.get("maintenance"):
        raise ValueError("Mag rotation requires SSLOG and a maintenance UART")
    if not any(stream.record == "FLIGHT_LOG_RECORD_EVENT" and stream.enabled and
               stream.policy.upper() == "EVENT" for stream in CompactLogStreams_Get(model)):
        raise ValueError("Mag rotation requires the enabled EVENT log stream with its event policy")
    if not any(part in model.mcu for part in ("stm32f4", "stm32h7")):
        raise ValueError("Mag rotation supports STM32F4/H7 edge timestamp providers")
