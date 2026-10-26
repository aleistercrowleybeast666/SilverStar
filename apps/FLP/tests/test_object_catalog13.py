import copy
import hashlib
import json

import pytest

from silverstar_flp.decoder_profiles.object_catalog import ObjectCatalog_Validate
from silverstar_data_contracts.objects import ObjectCatalog_DefaultGet
from silverstar_flp.decoder_profiles.package import DecoderProfilePackage
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from tests.test_decoder_profiles import _PackageFiles_Build, _Package_Write, _JsonBytes, _Checksums_Refresh


def upgraded_files():
    files, _ = _PackageFiles_Build()
    document = ObjectCatalog_DefaultGet()
    objects = _JsonBytes(document)
    manifest = json.loads(files['manifest.json'])
    manifest['package_schema'] = dict(id='silverstar.ssdecoder.package-schema/1.3', major=1, minor=3)
    manifest['entries'].append('object_catalog.json')
    manifest['object_catalog_sha256'] = hashlib.sha256(objects).hexdigest()
    manifest['generation_profile_sha256'] = hashlib.sha256(
        b'silverstar.ssdecoder.package-schema/1.3\nsilverstar.sslog.container/0.0\n'
        + bytes.fromhex(manifest['record_catalog_sha256'])
        + bytes.fromhex(manifest['project_semantics_sha256'])
        + bytes.fromhex(manifest['object_catalog_sha256'])).hexdigest()
    files['object_catalog.json'] = objects
    files['manifest.json'] = _JsonBytes(manifest)
    _Checksums_Refresh(files)
    return files


def test_legacy12_and_new13_members_and_hashes(tmp_path):
    old, _ = _PackageFiles_Build()
    old_path = tmp_path / 'old.ssdecoder'
    _Package_Write(old_path, files=old)
    old_hash = hashlib.sha256(old_path.read_bytes()).hexdigest()
    legacy = DecoderProfilePackage.Load(old_path)
    assert legacy.package_schema_minor == 2
    assert legacy.object_catalog is None
    new_path = tmp_path / 'new.ssdecoder'
    _Package_Write(new_path, files=upgraded_files())
    current = DecoderProfilePackage.Load(new_path)
    assert current.package_schema_minor == 3
    assert len(current.member_names) == 6
    assert current.object_catalog['schema_id'] == 'silverstar.object-catalog/1.0'
    assert hashlib.sha256(old_path.read_bytes()).hexdigest() == old_hash
    assert current.generation_profile_sha256 != legacy.generation_profile_sha256


def test_object_catalog_tamper_detected_even_after_checksums_refresh(tmp_path):
    files = upgraded_files()
    objects = json.loads(files['object_catalog.json'])
    objects['rules']['calibration_results'] += ' tampered'
    files['object_catalog.json'] = _JsonBytes(objects)
    _Checksums_Refresh(files)
    path = tmp_path / 'tampered.ssdecoder'
    _Package_Write(path, files=files)
    with pytest.raises(DecoderProfileError, match='decoder_object_catalog_hash_mismatch'):
        DecoderProfilePackage.Load(path)
    manifest = json.loads(files['manifest.json'])
    manifest['object_catalog_sha256'] = hashlib.sha256(files['object_catalog.json']).hexdigest()
    files['manifest.json'] = _JsonBytes(manifest)
    _Checksums_Refresh(files)
    _Package_Write(path, files=files)
    with pytest.raises(DecoderProfileError, match='decoder_generation_profile_hash_mismatch'):
        DecoderProfilePackage.Load(path)


def test_old_schema_cannot_smuggle_sixth_member(tmp_path):
    files = upgraded_files()
    manifest = json.loads(files['manifest.json'])
    manifest['package_schema'] = dict(id='silverstar.ssdecoder.package-schema/1.2', major=1, minor=2)
    files['manifest.json'] = _JsonBytes(manifest)
    _Checksums_Refresh(files)
    path = tmp_path / 'bad-legacy.ssdecoder'; _Package_Write(path, files=files)
    with pytest.raises(DecoderProfileError, match='unexpected_member'):
        DecoderProfilePackage.Load(path)


@pytest.mark.parametrize('field,value', [('offset', 1), ('count', 1000000), ('type', 'script'), ('type', [])])
def test_object_layout_rejects_invalid_fields(field, value):
    objects = copy.deepcopy(ObjectCatalog_DefaultGet())
    objects['objects'][0]['fields'][0][field] = value
    with pytest.raises(ValueError): ObjectCatalog_Validate(objects)


def test_actual_scg_generator_to_flp13(tmp_path):
    from pathlib import Path
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.generator.render import LogDecoderProfile_Render
    from silverstar_fccg.generator.log_decoder_profile import LogDecoderPackage_Verify
    root = Path(__file__).resolve().parents[2] / 'SCG'
    service = FccgService(root)
    model = service.ReferenceProject_Create('ObjectCatalog13')
    result = LogDecoderProfile_Render(model, service.catalog)
    manifest = LogDecoderPackage_Verify(result.content)
    assert manifest['package_schema']['minor'] == 3
    path = tmp_path / 'actual.ssdecoder'; path.write_bytes(result.content)
    opened = DecoderProfilePackage.Load(path)
    assert opened.generation_profile_sha256 == result.generation_profile_sha256
    assert len(opened.member_names) == 6


def test_automatic13_exact_cache_then_project_directory_and_explicit_priority(tmp_path):
    from tests.test_decoder_profiles import (_DescriptorPayload_Build, _CalibrationNonePayload_Build,
        builtin_registry, DESCRIPTOR_RECORD_TYPE, START_TIMESTAMP_US)
    from tests.sslog_synthetic import SyntheticSslogBuilder, Event_Payload
    from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
    from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
    task = tmp_path/'task'; task.mkdir()
    projects = tmp_path/'projects'; projects.mkdir()
    source, hashes = _Package_Write(projects/'renamed.ssdecoder', files=upgraded_files())
    builder = SyntheticSslogBuilder()
    # Package schema minor is explicitly 3 in the new Descriptor.
    descriptor = bytearray(_DescriptorPayload_Build(hashes)); descriptor[2:4] = b'\x03\x00'
    builder.Record_Add(DESCRIPTOR_RECORD_TYPE, bytes(descriptor), START_TIMESTAMP_US - 3)
    builder.Record_Add(0x17, _CalibrationNonePayload_Build(), START_TIMESTAMP_US - 2)
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    log = builder.File_Write(task/'flight.sslog')
    cache = DecoderProfileCache(tmp_path/'cache')
    coordinator = LogOpenCoordinator(builtin_registry(), cache=cache)
    opened = coordinator.Open(LogOpenRequest(log_path=log, auto_find=True,
        decoder_search_directories=(projects,)))
    assert opened.package.package_schema_minor == 3
    # The exact cache works without a package beside the log or search path.
    reopened = coordinator.Open(LogOpenRequest(log_path=log, auto_find=True))
    assert reopened.package.package_sha256 == opened.package.package_sha256
    bad = task/'explicit.ssdecoder'; bad.write_bytes(b'bad explicit package')
    with pytest.raises(DecoderProfileError):
        coordinator.Open(LogOpenRequest(log_path=log, decoder_package_path=bad))
