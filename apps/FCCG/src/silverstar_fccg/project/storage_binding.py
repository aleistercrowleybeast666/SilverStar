from __future__ import annotations

import re
from dataclasses import dataclass

from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import ProjectModel
from silverstar_fccg.project.resources import ResourceAssignments_Resolve


@dataclass(frozen=True, slots=True)
class StorageBindingIssue:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class StorageBindingResult:
    object_symbol: str = ""
    path_symbol: str = ""
    driver_symbol: str = ""
    issues: tuple[StorageBindingIssue, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.issues


def StorageBinding_Resolve(model: ProjectModel, catalog: PluginCatalog) -> StorageBindingResult:
    """One generation prerequisite, shared by validation and header rendering.

    This checks declared physical storage/FatFs binding, not a card's runtime
    presence or health. TF/START hardware verification remains authoritative.
    """
    def reject(code: str, message: str) -> StorageBindingResult:
        return StorageBindingResult(issues=(StorageBindingIssue(code, message),))

    try:
        instances = tuple(instance for instance in model.device_instances
                          if "service.storage" in catalog.InstanceComponent_Get(instance).provides)
    except ValueError:
        return reject("STORAGE_COMPONENT_UNAVAILABLE",
                      "Restore the unavailable device plugin before checking storage / "
                      "请先恢复缺失的设备插件，再检查存储配置。")
    if len(instances) != 1:
        return reject("STORAGE_DEVICE_REQUIRED" if not instances else "STORAGE_DEVICE_AMBIGUOUS",
                      "Select exactly one physical TF/SD storage device and bind its SDIO resource; "
                      "storage is required even when flight logging is disabled / "
                      "请选择且仅选择一个物理 TF/SD 存储设备，并绑定 SDIO 资源；关闭飞行日志仍需要存储服务。")
    try:
        resolution = ResourceAssignments_Resolve(model, catalog)
    except ValueError:
        return reject("STORAGE_RESOURCE_INVALID",
                      "Restore the hardware/resource configuration before binding storage / "
                      "请先修复硬件与资源配置，再绑定存储设备。")
    assignment = next((item for item in resolution.assignments
                       if item.component_id == instances[0].instance_id
                       and item.requirement.kind == "sdio"), None)
    if assignment is None:
        return reject("STORAGE_SDIO_UNBOUND",
                      "Bind the storage device to a valid SDIO resource / "
                      "请为存储设备绑定有效的 SDIO 资源。")
    fatfs = assignment.provision.metadata.get("fatfs", {})
    fields = ("object_symbol", "path_symbol", "driver_symbol")
    if (not isinstance(fatfs, dict) or fatfs.get("enabled") is not True
            or fatfs.get("errors") or any(not isinstance(fatfs.get(name), str)
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fatfs[name]) is None for name in fields)):
        return reject("STORAGE_FATFS_INVALID",
                      "Import/configure CubeMX SDIO + FatFs with unique valid App/Target object, "
                      "path and driver symbols / 请导入或配置 CubeMX SDIO + FatFs，"
                      "确保 App/Target 的对象、路径和驱动符号唯一且有效。")
    return StorageBindingResult(*(fatfs[name] for name in fields))
