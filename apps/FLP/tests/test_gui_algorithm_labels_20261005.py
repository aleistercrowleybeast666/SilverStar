from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.algorithm_labels import AlgorithmName_Display


def test_algorithm_labels_preserve_registry_identity():
    registry = builtin_registry()
    labels = {plugin.metadata.plugin_id: plugin.metadata.display_name
              for plugin in registry.algorithms}
    assert labels["silverstar.algorithm.kf6"] == "KF_6"
    assert labels["silverstar.algorithm.estimator.eskf15"] == "ESKF_15"
    assert AlgorithmName_Display(labels["silverstar.algorithm.kf6"]) == "KF6"
    assert AlgorithmName_Display(labels["silverstar.algorithm.estimator.eskf15"]) == "ESKF15"
    assert AlgorithmName_Display("Pure INS / KF_6") == "Pure INS / KF6"
