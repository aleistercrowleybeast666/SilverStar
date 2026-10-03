from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from silverstar_flp.plugins.api.algorithm import AlgorithmPlugin
from silverstar_flp.plugins.api.log_container import LogContainerPlugin


@dataclass(slots=True)
class PluginRegistry:
    _log_containers: dict[str, LogContainerPlugin] = field(default_factory=dict)
    _algorithms: dict[str, AlgorithmPlugin] = field(default_factory=dict)

    def LogContainer_Register(self, plugin: LogContainerPlugin) -> None:
        plugin_id = plugin.metadata.plugin_id
        if plugin_id in self._log_containers:
            raise ValueError(f"duplicate_log_container:{plugin_id}")
        self._log_containers[plugin_id] = plugin

    def Algorithm_Register(self, plugin: AlgorithmPlugin) -> None:
        plugin_id = plugin.metadata.plugin_id
        if plugin_id in self._algorithms:
            raise ValueError(f"duplicate_algorithm:{plugin_id}")
        self._algorithms[plugin_id] = plugin

    @property
    def log_containers(self) -> tuple[LogContainerPlugin, ...]:
        return tuple(self._log_containers.values())

    @property
    def algorithms(self) -> tuple[AlgorithmPlugin, ...]:
        return tuple(self._algorithms.values())

    def LogContainer_Get(self, plugin_id: str) -> LogContainerPlugin:
        return self._log_containers[plugin_id]

    def Algorithm_Get(self, plugin_id: str) -> AlgorithmPlugin:
        return self._algorithms[plugin_id]

    def LogContainer_Probe(self, path: Path) -> LogContainerPlugin | None:
        try:
            with Path(path).open("rb") as source:
                ranked = sorted(
                    (
                        (plugin.probe(source).confidence, plugin)
                        for plugin in self.log_containers
                    ),
                    key=lambda item: item[0],
                    reverse=True,
                )
        except OSError:
            return None
        return ranked[0][1] if ranked and ranked[0][0] > 0.0 else None


def builtin_registry() -> PluginRegistry:
    from silverstar_flp.plugins.algorithms.eskf15.plugin import Eskf15AlgorithmPlugin
    from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
    from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
    from silverstar_flp.plugins.algorithms.sf6.plugin import Sf6AlgorithmPlugin
    from silverstar_flp.plugins.log_containers.sslog0.plugin import Sslog0ContainerPlugin

    registry = PluginRegistry()
    sslog0_container = Sslog0ContainerPlugin()
    registry.LogContainer_Register(sslog0_container)
    registry.Algorithm_Register(PureInsAlgorithmPlugin())
    registry.Algorithm_Register(Sf6AlgorithmPlugin())
    registry.Algorithm_Register(Kf6AlgorithmPlugin())
    registry.Algorithm_Register(Eskf15AlgorithmPlugin())
    return registry
