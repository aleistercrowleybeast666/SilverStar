from __future__ import annotations

from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import ProjectModel


COMPACT_DEVICE_CLASSES = frozenset({
    "SYSTEM_DEVICE_CLASS_IMU", "SYSTEM_DEVICE_CLASS_GNSS",
    "SYSTEM_DEVICE_CLASS_TELEMETRY", "SYSTEM_DEVICE_CLASS_BAROMETER",
})


def CompactErrors_Get(model: ProjectModel, catalog: PluginCatalog) -> tuple[str, ...]:
    """Bound capability endpoints, including endpoints of multifunction devices."""
    if not model.build.compact_mode:
        return ()
    catalog = catalog.ProjectView_Get(model)
    owners: dict[str, set[str]] = {kind: set() for kind in COMPACT_DEVICE_CLASSES}
    for instance in model.device_instances:
        manifest = catalog.InstanceComponent_Get(instance)
        for descriptor in manifest.metadata.get("device_descriptors", ()):
            kind = descriptor.get("class")
            if kind in owners:
                owners[kind].add(instance.instance_id)
    return tuple(
        f"Compact mode permits at most one {kind}: {', '.join(sorted(instances))}"
        for kind, instances in sorted(owners.items()) if len(instances) > 1
    )
