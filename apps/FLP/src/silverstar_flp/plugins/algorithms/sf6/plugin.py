"""Revision-aware SF6 replay; revision1 remains the frozen history implementation."""

from dataclasses import replace

from silverstar_flp.decoder_profiles.sf6_revision import Sf6Revision_Get
from silverstar_flp.plugins.algorithms.sf6.current_state import Sf6CurrentStateFilter
from silverstar_flp.plugins.algorithms.sf6.legacy_plugin import (
    DELAY_IDS, GAIN_IDS, STATE_ORDER, Sf6MeasurementTime_Resolve,
    Sf6AlgorithmPlugin as Sf6LegacyAlgorithmPlugin,
)
from silverstar_flp.plugins.api.algorithm import AlgorithmPlugin, ReplayMode


class Sf6AlgorithmPlugin(Sf6LegacyAlgorithmPlugin):
    metadata = replace(
        Sf6LegacyAlgorithmPlugin.metadata,
        version="0.2.0-c-core-revision2",
        description="Current-state fixed-gain ENU fusion; no delayed history replay",
        parameter_schema=tuple(p for p in Sf6LegacyAlgorithmPlugin.metadata.parameter_schema
                               if p.parameter_id not in DELAY_IDS),
        parameter_source_contract={
            "recorded_configuration": "exact decoder revision-specific SF6 gains + INS gravity",
            "offline": "revision2 current-state defaults, never recorded configuration",
        },
        cadence_contract={"max_dt_s": 0.02, "measurement_max_age_us": 500000,
                          "update_boundary": "latest prediction", "history_replay": False},
    )

    def _Legacy_Is(self, dataset):
        return Sf6Revision_Get(dataset) == 1

    def PluginForDataset_Get(self, dataset, mode=None):
        if dataset is not None and mode != ReplayMode.OFFLINE and self._Legacy_Is(dataset):
            return Sf6LegacyAlgorithmPlugin()
        return self

    def RuntimeParameterSchema_Get(self, dataset, quality_policy_revision=None):
        if dataset is not None and self._Legacy_Is(dataset):
            return Sf6LegacyAlgorithmPlugin.metadata.parameter_schema
        return self.metadata.parameter_schema

    def recorded_parameters(self, dataset):
        if self._Legacy_Is(dataset):
            return Sf6LegacyAlgorithmPlugin().recorded_parameters(dataset)
        return super().recorded_parameters(dataset)

    def ConfigurationAvailability_Get(self, dataset, *, input_available=True):
        if self._Legacy_Is(dataset):
            return Sf6LegacyAlgorithmPlugin().ConfigurationAvailability_Get(
                dataset, input_available=input_available)
        return super().ConfigurationAvailability_Get(dataset, input_available=input_available)

    def Parameters_Resolve(self, dataset, request):
        revision = Sf6Revision_Get(dataset)
        if revision == 1 and request.mode != ReplayMode.OFFLINE:
            return Sf6LegacyAlgorithmPlugin().Parameters_Resolve(dataset, request)
        if set(request.parameters) & set(DELAY_IDS):
            raise ValueError("sf6_revision2_delay_parameters_forbidden")
        # Explicit Offline mode always selects revision2 and its own defaults,
        # including when the attached firmware dataset is historical revision1.
        if request.mode == ReplayMode.OFFLINE:
            self.metadata.Parameters_Validate(request.parameters, complete=False)
            values = {**self.OfflineParameters_Get(), **request.parameters}
            self.metadata.Parameters_Validate(values)
            return values
        return AlgorithmPlugin.Parameters_Resolve(self, dataset, request)

    def _Core_Build(self, gain, velocity, timestamp_us):
        return Sf6CurrentStateFilter(gain, velocity, timestamp_us)

    def _Observations_Build(self, dataset, parameters, recorded, warnings):
        # The old builder's exact recorded epoch path is reused; raw cross-
        # algorithm observations resolve trusted sample time or receive time.
        zeros = dict.fromkeys(DELAY_IDS, 0)
        observations = super()._Observations_Build(dataset, {**parameters, **zeros},
                                                  {**recorded, **zeros}, warnings)
        warnings[:] = ["sf6_timestamp_trust_missing_receive_only_revision2"
                       if value == "sf6_timestamp_trust_missing_receive_only" else value
                       for value in warnings]
        return observations

    def run(self, dataset, request, context=None):
        revision = Sf6Revision_Get(dataset)
        if revision == 1 and request.mode != ReplayMode.OFFLINE:
            result = Sf6LegacyAlgorithmPlugin().run(dataset, request, context)
            return replace(result, diagnostics={**result.diagnostics,
                "algorithm_revision": 1, "fusion_semantics": "fixed-lag-history-replay"})
        result = super().run(dataset, request, context)
        diagnostics = dict(result.diagnostics)
        for key in ("history_window_us", "history_capacity", "event_capacity"):
            diagnostics.pop(key, None)
        diagnostics.update({"algorithm_revision": 2,
            "dataset_algorithm_revision": revision,
            "fusion_semantics": "current-state-no-history-replay",
            "measurement_max_age_us": 500000,
            "update_boundary": "latest prediction",
            "source_epoch_use": "age and per-group order validation only",
            "delay_parameters": "not supported",
            "lag_error": "Delayed observations correct current state without transport compensation."})
        warnings = (*result.warnings, "sf6_delayed_measurements_not_compensated")
        if revision == 1:
            warnings = (*warnings, "sf6_revision1_explicit_offline_revision2")
        return replace(result, diagnostics=diagnostics, warnings=warnings)
