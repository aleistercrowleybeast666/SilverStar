"""Opt-in actual C SF6 backend/LoggerTask log, exact generated decoder only."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry


@pytest.mark.skipif(not os.environ.get("SILVERSTAR_SF6_ACTUAL_ROOT"), reason="requires explicitly generated actual SF6 C fixture")
def test_actual_sf6_backend_exact_decoder_and_recorded_sources(tmp_path):
    root = Path(os.environ["SILVERSTAR_SF6_ACTUAL_ROOT"])
    log = root / os.environ.get("SILVERSTAR_SF6_LOG", "SF6_ACTUAL_BACKEND_v3.BIN")
    packages = tuple((root / os.environ.get("SILVERSTAR_SF6_PROJECT", "SF6_Probe_v1")).glob("*.ssdecoder"))
    assert len(packages) == 1
    package = packages[0]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (log, package)}
    coordinator = LogOpenCoordinator(builtin_registry(), cache=DecoderProfileCache(tmp_path / "cache"))
    opened = coordinator.Open(LogOpenRequest(log_path=log, decoder_package_path=package))
    dataset = opened.dataset
    states = dataset.Records_Get("SF6_STATE")
    measurements = dataset.Records_Get("SF6_MEASUREMENT")
    assert len(states) == 1000 and len(measurements) == 104
    assert len(dataset.Records_Get("DECODER_PROFILE_DESCRIPTOR")) == 1
    calibration = dataset.Records_Get("CALIBRATION_RESULT")
    assert len(calibration) == 1
    assert calibration[0].payload["mode"] == 0 and calibration[0].payload["ready"] == 1
    assert tuple(calibration[0].payload["accel_scale"]) == (1.0, 1.0, 1.0)
    assert tuple(calibration[0].payload["gyro_scale"]) == (1.0, 1.0, 1.0)
    assert all(record.payload["algorithm_id"] == 3 for record in states)
    assert all(tuple(record.payload["gain"]) == pytest.approx((0.2,) * 6) for record in states)
    assert not dataset.Records_Get("ESTIMATOR")
    assert not dataset.Records_Get("ESKF15_STATE")
    assert not dataset.Series_Get("sf6.recorded.covariance.diagonal")
    resolver = ChannelResolver(dataset, ReplayResultStore())
    assert resolver.RecordedNavigationSources_Get() == ("SF6",)
    assert resolver.RecordedNavigationSource_Get() == "SF6"
    for channel, field in [("navigation.position_enu", "position_enu_m"), ("navigation.velocity_enu", "velocity_enu_mps")]:
        series = resolver.RecordedSeries_Get(channel, solution="sf6")
        assert series is not None and series.count == 1000
        np.testing.assert_allclose(series.values, [r.payload[field] for r in states], atol=0, rtol=0)
        assert np.isfinite(series.values).all()
        assert resolver.RecordedSeries_Get(channel) is series
    successful = [r.payload for r in measurements if r.payload["result"] == 0]
    assert successful
    assert all(p["boundary_timestamp_us"] <= p["measurement_timestamp_us"] <= p["receive_timestamp_us"] <= p["evaluation_timestamp_us"] for p in successful)
    assert all(p["measurement_timestamp_us"] - p["boundary_timestamp_us"] <= 20000 for p in successful)
    assert any(p["group"] == 4 for p in successful)
    for p, digest in before.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest
    wrong = tuple((root / "KF6_v6").glob("*.ssdecoder"))
    assert len(wrong) == 1
    with pytest.raises(DecoderProfileError):
        coordinator.Open(LogOpenRequest(log_path=log, decoder_package_path=wrong[0]))
    with pytest.raises(DecoderProfileError):
        LogOpenCoordinator(builtin_registry(), cache=DecoderProfileCache(tmp_path / "empty_cache")).Open(LogOpenRequest(log_path=log))
