from __future__ import annotations

from pathlib import Path

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import DecodedRecord, FlightDataset, FlightDatasetBuilder
from silverstar_flp.core.diagnostics import DiagnosticSeverity, ParserDiagnostics
from silverstar_flp.decoder_profiles.descriptor import DecoderProfileDescriptor
from silverstar_flp.decoder_profiles.errors import DecoderProfileError, RecordDecodeError
from silverstar_flp.decoder_profiles.package import DecoderProfilePackage
from silverstar_flp.plugins.api.log_container import (
    ContainerError,
    LogContainerPlugin,
    ParseOptions,
    RawRecordFrame,
)
from silverstar_flp.plugins.api.log_parser import LogParserMetadata, LogParserPlugin, ParserError

_DESCRIPTOR_RECORD_NAME = "DECODER_PROFILE_DESCRIPTOR"


class DecoderProfileParserPlugin(LogParserPlugin):
    """Pure-data record decoder composed with one trusted container plugin."""

    def __init__(
        self,
        container: LogContainerPlugin,
        package: DecoderProfilePackage,
    ) -> None:
        package.Container_Validate(container)
        self.container = container
        self.package = package
        self.metadata = LogParserMetadata(
            plugin_id="silverstar.log_parser.decoder_profile",
            version="1.1.0",
            display_name=str(
                package.manifest.get("display_name", package.semantics.project_name)
                or "SilverStar Decoder Profile"
            ),
            description="Configuration-driven SilverStar flight-log parser",
            supported_profiles=(0,),
        )

    def probe(self, path: Path) -> float:
        try:
            with Path(path).open("rb") as source:
                return self.container.probe(source).confidence
        except OSError:
            return 0.0

    def parse(self, path: Path, context: TaskContext | None = None) -> FlightDataset:
        parse_context = context or TaskContext()
        source_path = Path(path)
        diagnostics = ParserDiagnostics()
        builder = FlightDatasetBuilder()
        partial = False
        descriptor: DecoderProfileDescriptor | None = None
        descriptor_error: DecoderProfileError | None = None
        try:
            file_size = source_path.stat().st_size
            with source_path.open("rb") as source:
                options = ParseOptions(
                    diagnostics=diagnostics,
                    context=parse_context,
                    source_size=file_size,
                    maximum_payload_length=max(
                        layout.payload_size
                        for layout in self.package.catalog.layouts.values()
                    ),
                )
                header = self.container.header_read(source, options)
                header_record_limit = int(header.get("maximum_record_size", 0))
                options.maximum_payload_length = min(
                    1_048_576,
                    max(
                        options.maximum_payload_length,
                        header_record_limit,
                    ),
                )
                for frame in self.container.iter_frames(source, options):
                    try:
                        bootstrap_descriptor = DecoderProfileDescriptor.FromRawPayload(
                            frame.record_type,
                            frame.record_version,
                            frame.payload_bytes,
                        )
                        if bootstrap_descriptor is not None:
                            if descriptor is not None and bootstrap_descriptor != descriptor:
                                raise DecoderProfileError(
                                    "decoder_profile_descriptor_conflict"
                                )
                            descriptor = bootstrap_descriptor
                    except DecoderProfileError as exc:
                        descriptor_error = exc
                    layout = self.package.catalog.Layout_Get(
                        frame.record_type,
                        frame.record_version,
                    )
                    if layout is None:
                        partial = True
                        record = self._UnknownRecord_Build(frame)
                        self._UnknownRecord_DiagnosticAdd(frame, diagnostics)
                        builder.Record_Add(record)
                        continue
                    try:
                        payload = layout.Decode(frame.payload_bytes)
                    except RecordDecodeError as exc:
                        partial = True
                        diagnostics.decoder_failure_count += 1
                        diagnostics.Diagnostic_Add(
                            exc.code,
                            DiagnosticSeverity.WARNING,
                            offset=frame.source_offset,
                            record_sequence=frame.sequence,
                            record_type=frame.record_type,
                            record_version=frame.record_version,
                            payload_length=frame.payload_length,
                            expected_length=layout.payload_size,
                            error=exc.details,
                        )
                        builder.Record_Add(
                            self._PartialRecord_Build(frame, layout.name, exc.code)
                        )
                        continue

                    record = DecodedRecord(
                        record_type=frame.record_type,
                        record_name=layout.name,
                        record_version=frame.record_version,
                        payload_length=frame.payload_length,
                        record_sequence=frame.sequence,
                        timestamp_us=frame.timestamp_us,
                        valid_flags=frame.valid_flags,
                        payload=payload,
                        file_offset=frame.source_offset,
                    )
                    try:
                        definitions = self.package.semantics.ChannelDefinitions_Get(
                            layout.name,
                            payload,
                        )
                    except DecoderProfileError as exc:
                        partial = True
                        definitions = ()
                        diagnostics.decoder_failure_count += 1
                        diagnostics.Diagnostic_Add(
                            exc.code,
                            DiagnosticSeverity.WARNING,
                            offset=frame.source_offset,
                            record_sequence=frame.sequence,
                            record_type=frame.record_type,
                            record_version=frame.record_version,
                            error=exc.details,
                        )
                    builder.Record_Add(record, definitions)
                    diagnostics.decoded_record_count += 1
                    if layout.name == _DESCRIPTOR_RECORD_NAME:
                        try:
                            current_descriptor = DecoderProfileDescriptor.FromPayload(payload)
                            if descriptor is not None and current_descriptor != descriptor:
                                raise DecoderProfileError(
                                    "decoder_profile_descriptor_conflict"
                                )
                            descriptor = current_descriptor
                        except DecoderProfileError as exc:
                            descriptor_error = exc
        except OSError as exc:
            raise ParserError("log_open_failed", str(exc)) from exc
        except ContainerError as exc:
            raise ParserError(exc.code, exc.details) from exc

        if descriptor_error is not None:
            raise ParserError(
                "decoder_profile_descriptor_invalid",
                str(descriptor_error),
            ) from descriptor_error
        if descriptor is None:
            raise ParserError("decoder_profile_descriptor_missing")
        try:
            descriptor.PackageExactMatch_Validate(self.package)
        except DecoderProfileError as exc:
            raise ParserError(exc.code, exc.details) from exc
        match_mode = "exact_generation_profile"

        parse_context.Progress_Report(0.99, "parser.dataset")
        dataset = builder.Build(
            source_path=source_path,
            file_size=file_size,
            header=header,
            diagnostics=diagnostics,
            metadata={
                "parser_plugin_id": self.metadata.plugin_id,
                "parser_plugin_version": self.metadata.version,
                "container_plugin_id": self.container.metadata.plugin_id,
                "container_plugin_version": self.container.metadata.version,
                "container_generation": self.container.metadata.container_format_id,
                "decoder_profile_declared_container_plugin_id": (
                    self.package.declared_container_plugin_id
                ),
                "decoder_profile_path": str(self.package.source_path),
                "decoder_profile_package_sha256": self.package.package_sha256,
                "decoder_profile_generation_sha256": (
                    self.package.generation_profile_sha256
                ),
                "decoder_profile_generation_hash_128": (
                    self.package.generation_profile_hash_128
                ),
                "decoder_profile_record_catalog_hash_128": (
                    self.package.record_catalog_hash_128
                ),
                "decoder_profile_project_semantics_hash_128": (
                    self.package.project_semantics_hash_128
                ),
                "decoder_profile_project": self.package.semantics.project_name,
                "decoder_profile_firmware_version": (
                    self.package.semantics.firmware_version
                ),
                "decoder_profile_match_mode": match_mode,
                "parse_status": (
                    "partial"
                    if partial or diagnostics.has_integrity_warnings
                    else "complete"
                ),
                "synthetic": False,
            },
        )
        parse_context.Progress_Report(1.0, "parser.complete")
        return dataset

    def _UnknownRecord_DiagnosticAdd(
        self,
        frame: RawRecordFrame,
        diagnostics: ParserDiagnostics,
    ) -> None:
        if self.package.catalog.HasRecordType(frame.record_type):
            diagnostics.unknown_record_version_count += 1
            code = "unknown_record_version"
        else:
            diagnostics.unknown_record_type_count += 1
            code = "unknown_record_type"
        diagnostics.Diagnostic_Add(
            code,
            DiagnosticSeverity.INFO,
            offset=frame.source_offset,
            record_sequence=frame.sequence,
            record_type=frame.record_type,
            record_version=frame.record_version,
            payload_length=frame.payload_length,
            raw_payload_retained=True,
        )

    @staticmethod
    def _UnknownRecord_Build(frame: RawRecordFrame) -> DecodedRecord:
        return DecoderProfileParserPlugin._PartialRecord_Build(
            frame,
            f"UNKNOWN_0x{frame.record_type:02X}_V{frame.record_version}",
            "unknown_record_layout",
        )

    @staticmethod
    def _PartialRecord_Build(
        frame: RawRecordFrame,
        record_name: str,
        reason: str,
    ) -> DecodedRecord:
        return DecodedRecord(
            record_type=frame.record_type,
            record_name=record_name,
            record_version=frame.record_version,
            payload_length=frame.payload_length,
            record_sequence=frame.sequence,
            timestamp_us=frame.timestamp_us,
            valid_flags=frame.valid_flags,
            payload={
                "raw_payload": frame.payload_bytes,
                "__partial__": True,
                "__partial_reason__": reason,
            },
            file_offset=frame.source_offset,
        )
