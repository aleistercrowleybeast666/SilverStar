"""Strict headless entry point; source SSLOG/package never become derived output."""
import argparse
import hashlib
import json
from pathlib import Path

from silverstar_flp.core.analysis_source import ReplayResultStore
from silverstar_flp.core.artifacts import Artifact_Write, FileHash_Get
from silverstar_flp.core.replay_execution import Replay_Execute
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest, LogOpenSourceMode
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit-input host navigation; derived outputs only")
    parser.add_argument('--log', required=True, type=Path)
    parser.add_argument('--decoder', required=True, type=Path)
    configuration_group = parser.add_mutually_exclusive_group()
    configuration_group.add_argument('--configuration', type=Path)
    configuration_group.add_argument('--scg-initialization', type=Path,
        help='Explicit initial_navigation and observations JSON; requires --mode what_if')
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--model', choices=('eskf20','inekf15','inekf20'), required=True)
    parser.add_argument('--mode', choices=('offline','what_if','recorded_configuration'), default='offline')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.suffix != '.json' or output.exists():
        raise ValueError('navigation_new_derived_json_output_required')
    if not output.parent.is_dir():
        raise ValueError('navigation_output_parent_missing')
    configuration_path = args.configuration or args.scg_initialization
    if args.scg_initialization and args.mode != "what_if":
        raise ValueError("scg_conversion_requires_what_if")
    recorded = args.mode == 'recorded_configuration'
    if recorded and configuration_path is not None:
        raise ValueError('recorded_configuration_override_forbidden')
    if not recorded and configuration_path is None:
        raise ValueError('navigation_explicit_configuration_required')
    config_text, config_hash = '', None
    if configuration_path is not None:
        if configuration_path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError('navigation_configuration_too_large')
        config_bytes = configuration_path.read_bytes()
        if len(config_bytes) > 4 * 1024 * 1024:
            raise ValueError('navigation_configuration_too_large')
        config_text = config_bytes.decode('utf-8')
        config_hash = hashlib.sha256(config_bytes).hexdigest()
    registry = builtin_registry()
    opened = LogOpenCoordinator(registry, cache=DecoderProfileCache(args.cache)).Open(
        LogOpenRequest(args.log, args.decoder, source_mode=LogOpenSourceMode.CLI))
    plugin = registry.Algorithm_Get('silverstar.algorithm.estimator.' + args.model)
    if recorded:
        request = ReplayRequest(ReplayMode.RECORDED_CONFIGURATION,'navigation_journal')
    elif args.scg_initialization:
        from .plugin import _Json_Read
        supplied = _Json_Read(config_text)
        required = {"initial_navigation", "observations"}
        if not isinstance(supplied, dict) or not required <= set(supplied) <= required | {"body_input_assumption"}:
            raise ValueError("scg_initialization_document_fields")
        request = plugin.FirmwareConfiguration_WhatIfBuild(opened.dataset, supplied["initial_navigation"], supplied["observations"], body_input_assumption=supplied.get("body_input_assumption"))
    else:
        request = ReplayRequest(ReplayMode(args.mode), 'corrected_imu', {'configuration_json': config_text})
    result = Replay_Execute(plugin, opened.dataset, request)
    store = ReplayResultStore()
    entry = store.Result_Add(result, algorithm_name=plugin.metadata.display_name)
    identity = {'schema':'silverstar.navigation-derived-result/1',
        'source_log_sha256':opened.dataset.metadata['source_log_sha256'],
        'decoder_package_sha256':opened.package.package_sha256,
        'configuration_sha256':result.diagnostics['journal_sha256'] if recorded else hashlib.sha256(request.parameters['configuration_json'].encode()).hexdigest(),
        'algorithm_id':result.algorithm_id,
        'algorithm_version':result.algorithm_version}
    artifact = Artifact_Write(output, result, identity)
    manifest = {**identity, 'provenance':'Derived/recorded operation journal' if recorded else 'Derived/user configuration',
        'source_log':str(args.log.resolve()), 'source_decoder':str(args.decoder.resolve()),
        'source_configuration':str(configuration_path.resolve()) if configuration_path is not None else None, 'source_configuration_sha256':config_hash,
        'configuration_source_mode':'recorded_operation_journal' if recorded else 'scg_actual_parameters_explicit_what_if' if args.scg_initialization else 'explicit_json',
        'result_id':entry.result_id, 'artifact':artifact,
        'input_contract':result.diagnostics['input_contract'],
        'firmware_equivalence':'NOT_PROVEN'}
    with output.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, allow_nan=False, indent=2)
    print(str(output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
