from __future__ import annotations

from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import ProjectModel
from silverstar_fccg.project.feature_tiers import FeatureTier_DescriptorActive, FeatureTier_DeviceClassLimitGet


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
    classes: dict[str, set[str]] = {}
    for instance in model.device_instances:
        manifest = catalog.InstanceComponent_Get(instance)
        limit = FeatureTier_DeviceClassLimitGet(model.build.feature_tier, manifest.component_class,
            str(manifest.metadata.get("device_category", "")), 2)
        if limit <= 1:
            classes.setdefault(manifest.component_class, set()).add(instance.instance_id)
        for descriptor in manifest.metadata.get("device_descriptors", ()):
            kind = descriptor.get("class")
            if kind in owners and FeatureTier_DescriptorActive(model, catalog, instance.instance_id, kind):
                owners[kind].add(instance.instance_id)
    return tuple(
        f"Compact mode permits at most one {kind}: {', '.join(sorted(instances))}"
        for kind, instances in sorted(owners.items()) if len(instances) > 1
    ) + tuple(f"Tier permits at most one {kind}: {', '.join(sorted(instances))}"
              for kind, instances in sorted(classes.items()) if len(instances) > 1)
