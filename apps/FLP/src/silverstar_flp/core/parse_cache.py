"""Full-dataset cache identities, always admitted by the strict log coordinator."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from silverstar_flp.core.artifacts import Artifact_Read, Artifact_Write, FileHash_Get, IdentityHash_Get
from silverstar_flp.core.dataset import FlightDataset

PARSE_SCHEMA = "silverstar.flp.full-dataset/1"


def ParserIdentity_Get() -> str:
    root = Path(__file__).resolve().parents[1]
    files = sorted((root / "decoder_profiles").glob("*.py"))
    files += sorted((root / "plugins/log_containers").rglob("*.py"))
    files += [root / "plugins/api/log_container.py", root / "plugins/api/log_parser.py"]
    files += [root / "core" / name for name in (
        "dataset.py", "diagnostics.py", "semantic_context.py", "semantic_columns.py", "parse_cache.py")]
    return IdentityHash_Get({str(path.relative_to(root)): FileHash_Get(path)
                             for path in files if path.is_file()})


def ParseIdentity_Get(log_path: Path, decoder_identity: dict, context=None) -> dict:
    return {"schema": PARSE_SCHEMA, "log_sha256": FileHash_Get(log_path, context),
            "log_bytes": Path(log_path).stat().st_size, "decoder": decoder_identity,
            "parser_identity": ParserIdentity_Get()}


def DatasetCache_Read(project_path, reference, identity, log_path, context=None) -> FlightDataset:
    dataset = Artifact_Read(project_path, reference, identity, context)
    if not isinstance(dataset, FlightDataset) or dataset.file_size != identity["log_bytes"]:
        raise ValueError("parse_cache_dataset_invalid")
    if not dataset.diagnostics.header_valid or dataset.semantic_context is None:
        raise ValueError("parse_cache_authority_missing")
    if dataset.metadata.get("parse_identity") != identity:
        raise ValueError("parse_cache_source_identity_invalid")
    package = dataset.semantic_context.package_identity
    decoder = identity["decoder"]
    for key in ("package_sha256", "generation_profile_sha256", "record_catalog_sha256",
                "project_semantics_sha256"):
        if getattr(package, key) != decoder[key]:
            raise ValueError("parse_cache_decoder_mismatch")
    count = 0
    for name, records in dataset.records.items():
        if not isinstance(name, str) or not isinstance(records, tuple):
            raise ValueError("parse_cache_records_invalid")
        for record in records:
            count += 1
            if (record.record_name != name or type(record.file_offset) is not int
                    or not 0 <= record.file_offset < dataset.file_size
                    or type(record.payload_length) is not int
                    or not 0 <= record.payload_length <= dataset.file_size - record.file_offset
                    or type(record.timestamp_us) is not int or not 0 <= record.timestamp_us < 2**64
                    or type(record.record_sequence) is not int or not 0 <= record.record_sequence < 2**32):
                raise ValueError("parse_cache_record_bounds_invalid")
    if count != dataset.diagnostics.record_count:
        raise ValueError("parse_cache_record_count_invalid")
    for span in dataset.diagnostics.damaged_spans:
        if not 0 <= span.start_offset <= span.end_offset <= dataset.file_size:
            raise ValueError("parse_cache_damage_bounds_invalid")
    # Paths are display metadata, never read authority from the serialized dataset.
    return replace(dataset, source_path=Path(log_path).resolve())


def DatasetCache_Write(project_path, dataset, identity, context=None):
    if dataset.file_size != identity["log_bytes"]:
        raise ValueError("parse_cache_source_size_mismatch")
    if dataset.metadata.get("parse_identity") != identity:
        raise ValueError("parse_cache_source_identity_invalid")
    reference = Artifact_Write(project_path, dataset, identity, context)
    DatasetCache_Read(project_path, reference, identity, dataset.source_path, context)
    return reference
