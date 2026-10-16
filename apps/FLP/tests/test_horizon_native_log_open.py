"""Fresh native mode2 CPU producers through the production exact-pair opener.

Compile receipts from the separately executed native backend regressions supply
the owning source graph. No staged mode/lag overrides or old log relabeling.
"""

import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.decoder_profiles import DecoderProfileCache
from silverstar_flp.decoder_profiles.fusion_timing import FusionTiming_FromSemantics
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.test_horizon_backend_numerics import _Covariance_FromParts

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module", params=["kf6", "eskf15"])
def opened_native(request, tmp_path_factory):
    algorithm = request.param
    family = "kf" if algorithm == "kf6" else "eskf"
    supplied = os.environ.get(
        "SILVERSTAR_HORIZON_NATIVE_" + family.upper() + "_TRACE_ROOT"
    ) or os.environ.get("SILVERSTAR_HORIZON_NATIVE_TRACE_ROOT")
    assert supplied, "Select fresh native backend compile receipts; native log proof is unavailable"
    trace_root = Path(supplied).resolve()
    (receipt_path,) = trace_root.glob(f"{family}_backend_horizon-O20/compile.json")
    original = json.loads(receipt_path.read_text(encoding="utf8"))
    assert original["native_configuration"] is True and original["exit_code"] == 0
    command = original["command"].copy()
    assert not any(
        arg.startswith(("-DSYSTEM_FUSION_TIMING_MODE=", "-DSYSTEM_FUSION_HORIZON_MS="))
        for arg in command
    )
    forced_header = Path(command[command.index("-include") + 1])
    project = forced_header.parents[2]
    assert (
        "SYSTEM_FUSION_TIMING_MODE"
        in (project / "Generated/Inc/project_algorithm_parameters.h").read_text()
    )
    output = tmp_path_factory.mktemp("native_" + algorithm)
    producer = FIXTURES / (algorithm + "_horizon_producer.c")
    old_source = next(
        arg
        for arg in command
        if arg.endswith(f"test_{'estimator' if family == 'kf' else 'eskf'}_horizon.c")
    )
    command[command.index(old_source)] = str(producer)
    command.insert(
        1, "-D" + family.upper() + '_HORIZON_FIXTURE_SOURCE="' + Path(old_source).as_posix() + '"'
    )
    target = output / "producer.exe"
    command[command.index("-o") + 1] = str(target)
    run = subprocess.run(command, capture_output=True, text=True, timeout=180)
    (output / "compile.json").write_text(
        json.dumps(
            dict(
                command=command,
                exit_code=run.returncode,
                stdout=run.stdout,
                stderr=run.stderr,
                native_compile_receipt=str(receipt_path),
                native_compile_receipt_sha256=sha256(receipt_path.read_bytes()).hexdigest(),
                producer_sha256=sha256(producer.read_bytes()).hexdigest(),
                bootstrap_sha256=sha256(
                    (FIXTURES / "horizon_log_bootstrap.h").read_bytes()
                ).hexdigest(),
            ),
            indent=2,
        ),
        encoding="utf8",
    )
    assert run.returncode == 0, run.stdout + run.stderr
    log = output / "native.sslog"
    run = subprocess.run([str(target), str(log)], capture_output=True, text=True, timeout=30)
    (output / "producer.json").write_text(
        json.dumps(
            dict(
                exit_code=run.returncode,
                stdout=run.stdout,
                stderr=run.stderr,
                executable_sha256=sha256(target.read_bytes()).hexdigest(),
            ),
            indent=2,
        ),
        encoding="utf8",
    )
    assert run.returncode == 0, run.stdout + run.stderr
    (decoder,) = project.glob("*.ssdecoder")
    before = {str(p): sha256(p.read_bytes()).hexdigest() for p in (log, decoder)}
    registry = builtin_registry()
    opened = LogOpenCoordinator(registry, cache=DecoderProfileCache(output / "cache")).Open(
        LogOpenRequest(log_path=log, decoder_package_path=decoder)
    )
    identity = FusionTiming_FromSemantics(opened.package.semantics.raw_metadata)
    assert identity.mode == 2 and identity.horizon_us == 300000
    assert opened.match_mode == "exact_generation_profile"
    assert {
        row.payload["source_id"] for row in opened.dataset.Records_Get("FUSION_HORIZON_STATUS")
    } == {0}
    plugin = registry.Algorithm_Get(
        "silverstar.algorithm." + ("kf6" if algorithm == "kf6" else "estimator.eskf15")
    )
    yield opened.dataset, plugin, algorithm, output
    assert {str(p): sha256(p.read_bytes()).hexdigest() for p in (log, decoder)} == before
    (output / "input_hashes.json").write_text(json.dumps(before, indent=2), encoding="utf8")


def test_native_exact_log_open_recorded_and_explicit_what_if(opened_native):
    dataset, plugin, algorithm, output = opened_native
    source = "recorded_inertial_increment" if algorithm == "kf6" else None
    availability = plugin.availability(dataset, source)
    assert availability.available, availability
    result = plugin.run(dataset, ReplayRequest(input_source=source))
    assert result.diagnostics["recorded_horizon_us"] == 300000
    assert result.diagnostics["history_replay_count"] == 0
    assert result.diagnostics["effective_update_count"] > 0
    assert result.diagnostics["output_feedback"] is False
    channel = result.channels[algorithm + ".covariance.upper_triangle"]
    assert channel.valid.all() and np.isfinite(channel.values).all()
    assert len(channel.values) == 80
    for index, timestamp in enumerate(channel.timestamp_us):
        state_name = "ESTIMATOR" if algorithm == "kf6" else "ESKF15_STATE"
        (state,) = (row for row in dataset.Records_Get(state_name) if row.timestamp_us == timestamp)
        for channel_name, field in (
            ("navigation.position_enu", "position_enu_m"),
            ("navigation.velocity_enu", "velocity_enu_mps"),
            ("attitude.q_nb", "q_nb"),
        ):
            np.testing.assert_allclose(
                result.channels[channel_name].values[index],
                state.payload[field],
                rtol=8e-5,
                atol=3e-6,
            )
        if algorithm == "kf6":
            (covariance,) = (
                row.payload["covariance_upper_triangle"]
                for row in dataset.Records_Get("KF6_FULL_P")
                if row.timestamp_us == timestamp
            )
        else:
            covariance = _Covariance_FromParts(dataset.Records_Get("ESKF15_FULL_P_PART"), state)[
                np.triu_indices(15)
            ]
            for attribute, field in (
                ("gyro_bias", "gyro_bias_radps"),
                ("accel_bias", "accel_bias_mps2"),
            ):
                np.testing.assert_allclose(
                    result.channels["eskf15." + attribute].values[index],
                    state.payload[field],
                    rtol=8e-5,
                    atol=3e-6,
                )
        np.testing.assert_allclose(channel.values[index], covariance, rtol=8e-5, atol=3e-6)
    changed = plugin.run(
        dataset,
        ReplayRequest(
            ReplayMode.WHAT_IF, input_source=source, parameters={"fusion_horizon_ms": 100}
        ),
    )
    assert changed.provenance == "What-if"
    assert changed.diagnostics["recorded_horizon_us"] == 300000
    assert changed.diagnostics["selected_horizon_us"] == 100000
    assert changed.diagnostics["history_replay_count"] == 0
    (output / "replay.json").write_text(
        json.dumps(
            dict(
                algorithm=algorithm,
                output_count=len(channel.values),
                fidelity=result.fidelity.value,
                recorded=result.diagnostics,
                what_if=changed.diagnostics,
            ),
            indent=2,
            default=str,
        ),
        encoding="utf8",
    )
