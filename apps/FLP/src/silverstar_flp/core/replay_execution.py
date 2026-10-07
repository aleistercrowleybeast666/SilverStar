"""Bind completed production replay to the exact input used at execution time."""
from dataclasses import replace

from silverstar_flp.core.artifacts import EngineIdentity_Get


def Replay_Execute(plugin, dataset, request, context=None):
    from silverstar_flp.core.semantic_context import _Immutable_Get, _JsonCompatible_Get
    input_identity = _Immutable_Get(_JsonCompatible_Get(dataset.metadata.get("parse_identity")))
    engine_identity = EngineIdentity_Get()
    result = plugin.run(dataset, request, context)
    return replace(result, diagnostics={**result.diagnostics,
        "input_identity": input_identity,
        "engine_identity": engine_identity,
        "run_request": {"mode": request.mode.value, "input_source": request.input_source,
                        "quality_policy_revision": request.quality_policy_revision,
                        "process_model_revision": request.process_model_revision}})
