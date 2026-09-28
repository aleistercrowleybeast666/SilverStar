from __future__ import annotations

import struct
from pathlib import Path

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import DecodedRecord, FlightDataset, FlightDatasetBuilder
from silverstar_flp.core.diagnostics import DiagnosticSeverity, ParserDiagnostics
from silverstar_flp.plugins.api.log_container import ContainerError, ParseOptions
from silverstar_flp.plugins.api.log_parser import LogParserMetadata, LogParserPlugin, ParserError
from silverstar_flp.plugins.log_containers.sslog0.plugin import Sslog0ContainerPlugin
from silverstar_flp.plugins.log_parsers.sslog0.records import (
    RECORD_DEFINITIONS,
    PayloadDecodeError,
)


class Sslog0ParserPlugin(LogParserPlugin):
    """Compatibility parser facade backed by the SSLOG0 container plugin.

    The facade preserves the existing GUI/CLI contract and legacy hard-coded
    record catalog. New decoder-profile parsing uses the same container plugin
    without depending on this legacy catalog.
    """

    metadata = LogParserMetadata(
        plugin_id="silverstar.log_parser.sslog0",
        version="0.2.0",
        display_name="SSLOG0",
        description="SilverStar Flight Log profile 0 parser",
        supported_profiles=(0,),
    )

    def __init__(self, container: Sslog0ContainerPlugin | None = None) -> None:
        self.container = container or Sslog0ContainerPlugin()

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
        try:
            file_size = source_path.stat().st_size
            with source_path.open("rb") as source:
                options = ParseOptions(
                    diagnostics=diagnostics,
                    context=parse_context,
                    source_size=file_size,
                )
                header = self.container.header_read(source, options)
                builder = FlightDatasetBuilder()
                for frame in self.container.iter_frames(source, options):
                    definition = RECORD_DEFINITIONS.get(frame.record_type)
                    if definition is None:
                        diagnostics.unknown_record_type_count += 1
                        diagnostics.Diagnostic_Add(
                            "unknown_record_type",
                            DiagnosticSeverity.INFO,
                            offset=frame.source_offset,
                            record_sequence=frame.sequence,
                            record_type=frame.record_type,
                            record_version=frame.record_version,
                            payload_length=frame.payload_length,
                        )
                        continue
                    if frame.record_version not in definition.common_versions:
                        diagnostics.unknown_record_version_count += 1
                        diagnostics.Diagnostic_Add(
                            "unknown_record_version",
                            DiagnosticSeverity.INFO,
                            offset=frame.source_offset,
                            record_sequence=frame.sequence,
                            record_type=frame.record_type,
                            record_version=frame.record_version,
                            payload_length=frame.payload_length,
                        )
                        continue
                    if frame.payload_length not in definition.payload_lengths:
                        diagnostics.decoder_failure_count += 1
                        diagnostics.Diagnostic_Add(
                            "record_payload_length_mismatch",
                            DiagnosticSeverity.WARNING,
                            offset=frame.source_offset,
                            record_sequence=frame.sequence,
                            record_type=frame.record_type,
                            payload_length=frame.payload_length,
                            expected_lengths=definition.payload_lengths,
                        )
                        continue
                    try:
                        payload = definition.decoder(frame.payload_bytes)
                    except (PayloadDecodeError, struct.error, ValueError) as exc:
                        diagnostics.decoder_failure_count += 1
                        diagnostics.Diagnostic_Add(
                            "record_decode_failure",
                            DiagnosticSeverity.WARNING,
                            offset=frame.source_offset,
                            record_sequence=frame.sequence,
                            record_type=frame.record_type,
                            error=str(exc),
                        )
                        continue

                    builder.Record_Add(
                        DecodedRecord(
                            record_type=frame.record_type,
                            record_name=definition.name,
                            record_version=frame.record_version,
                            payload_length=frame.payload_length,
                            record_sequence=frame.sequence,
                            timestamp_us=frame.timestamp_us,
                            valid_flags=frame.valid_flags,
                            payload=payload,
                            file_offset=frame.source_offset,
                        ),
                        definition.channels,
                    )
                    diagnostics.decoded_record_count += 1
        except OSError as exc:
            raise ParserError("log_open_failed", str(exc)) from exc
        except ContainerError as exc:
            raise ParserError(exc.code, exc.details) from exc

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
                "container_generation": "SSLOG0",
                "synthetic": False,
            },
        )
        parse_context.Progress_Report(1.0, "parser.complete")
        return dataset

    @staticmethod
    def _Header_Parse(
        header_bytes: bytes,
        diagnostics: ParserDiagnostics,
    ) -> dict[str, object]:
        options = ParseOptions(diagnostics=diagnostics)
        return Sslog0ContainerPlugin.Header_ParseBytes(header_bytes, options)
