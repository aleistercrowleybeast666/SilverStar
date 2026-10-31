from __future__ import annotations

import json
import hashlib
import zlib
import sys
from typing import Any
from pathlib import Path

from silverstar_fccg.project.model import ProjectModel
from silverstar_fccg.core.errors import FccgError


def ProjectGenerationState_Normalize(model: ProjectModel, target: str = 'flight') -> dict[str, Any]:
    """Return only the selected target's portable generation inputs.

    A Ground pin change cannot invalidate a Flight binary; shared PHY changes
    invalidate both. UI preferences and host executable paths are not firmware
    configuration. Build-affecting fields (including memory layout) remain.
    """
    if target not in ('flight', 'ground'):
        raise ValueError('Unknown generation target: ' + target)
    data = model.Dictionary_Get()
    data.pop("component_provenance", None)
    data.pop("reference_provenance", None)
    data.pop("log_decoder_profile", None)
    data.pop('feature_tier_presets', None)
    if target == 'ground':
        data = {'format_version': data['format_version'], 'project': data['project'],
                'ground_target': data['ground_target'], 'air_link': data['air_link'],
                'telemetry': data['protocols'].get('telemetry')}
        data['air_link'].pop('flight_radio_instance', None)
        hardware = data['ground_target']['hardware']
        build = data['ground_target']['build']
    else:
        data.pop('ground_target', None)
        hardware = data['hardware']
        build = data['build']
    hardware.pop("source_label", None)
    hardware.pop("risk_acknowledged", None)
    hardware.pop("assignment_fingerprint", None)
    hardware.pop("i2c_external_pullup_confirmations", None)
    for key in ('make_command', 'gcc_path', 'flash_command', 'tool_paths'):
        build.pop(key, None)
    # Project files are strict JSON, so tuple-backed in-memory inventory values
    # and their list-backed loaded representation describe the same state.
    # Normalize through JSON before direct readiness comparisons as well as
    # fingerprinting; otherwise opening a freshly generated project can make
    # its hardware inventory appear stale without any semantic change.
    return json.loads(json.dumps(data, ensure_ascii=False))


def ProjectGenerationFingerprint_Get(model: ProjectModel, target: str = 'flight') -> int:
    data = ProjectGenerationState_Normalize(model, target)
    canonical = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return zlib.crc32(canonical.encode("utf-8")) & 0xFFFFFFFF


def TargetGenerationInputHash_Get(model: ProjectModel, target: str) -> str:
    canonical = json.dumps(ProjectGenerationState_Normalize(model, target),
                           ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def ProjectDigest_Get(model: ProjectModel) -> int:
    """Compatibility name for the authoritative generation fingerprint."""
    return ProjectGenerationFingerprint_Get(model)


def _GenerationFilesHash_Get(files) -> str:
    digest = hashlib.sha256()
    for name, path in sorted(files, key=lambda item: item[0]):
        digest.update(name.encode('utf8')); digest.update(b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _GenerationAuthorityHash_Get() -> str:
    package = Path(__file__).resolve().parents[1]
    if getattr(sys, 'frozen', False):
        root = Path(sys._MEIPASS)
        files = [('frozen-generator-executable', Path(sys.executable))]
    else:
        root = Path(__file__).resolve().parents[5]
        files = [(path.relative_to(package).as_posix(), path)
                 for directory in ('generator', 'project', 'plugins')
                 for path in (package / directory).rglob('*.py')]
    files.extend(('contracts/' + path.name, path) for path in (root / 'contracts').glob('*.json'))
    files.extend(('tools/' + path.name, path) for path in (root / 'tools').glob('silverstar_mission_*.py'))
    return _GenerationFilesHash_Get(files)


def TargetGenerationReceipt_Get(model: ProjectModel, catalog, target: str) -> dict:
    """Full selected owner identities, including exact declarative payload bytes."""
    from silverstar_fccg.generator.render import ComponentProvenance_Get
    if target == 'flight':
        identities = set(model.ComponentIds_Get())
    elif target == 'ground':
        from silverstar_fccg.generator.multi_target import _GroundModel_Get
        identities = set(_GroundModel_Get(model, catalog).ComponentIds_Get())
        identities.update((model.core, 'silverstar.platform.api'))
    else:
        raise ValueError('Unknown target: ' + target)
    locks = {}
    for identity in sorted(identities):
        manifest = catalog.Component_Get(identity)
        templates = manifest.package_root / 'templates'
        locks[identity] = {'manifest_sha256': manifest.ManifestSha256_Get(),
            'payload_sha256': ComponentProvenance_Get(catalog, identity)['payload_digest'],
            'templates_sha256': _GenerationFilesHash_Get((path.relative_to(templates).as_posix(), path)
                for path in templates.rglob('*') if path.is_file())}
    return {'receipt_version': 2, 'target': target,
            'generation_authority_sha256': _GenerationAuthorityHash_Get(),
            'generation_input_sha256': TargetGenerationInputHash_Get(model, target),
            'component_locks': locks}


def ProjectTargetGenerated_IsCurrent(model: ProjectModel, catalog, root: Path, target: str) -> bool:
    """Compare the selected target's saved authority with current model and owners.

    Root is the generated target directory, not the multi-target project parent.
    Missing/legacy receipts are unknown and cannot enable build/quality readiness.
    """
    if target not in ('flight', 'ground'): raise ValueError('Unknown target: ' + target)
    name = 'memory_contract.json' if target == 'flight' else 'ground_target_metadata.json'
    try:
        value = json.loads((Path(root) / 'Generated' / name).read_text(encoding='utf-8'))
        if value.get('generation_input_sha256') != TargetGenerationInputHash_Get(model, target): return False
        expected = TargetGenerationReceipt_Get(model, catalog, target)
        return all(value.get(key) == item for key, item in expected.items())
    except (OSError, ValueError, KeyError, TypeError, FccgError):
        return False
