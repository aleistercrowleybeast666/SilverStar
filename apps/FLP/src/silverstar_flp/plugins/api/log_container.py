from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, BinaryIO

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.diagnostics import ParserDiagnostics


class ContainerError(RuntimeError):
    def __init__(self, code: str, details: str = "") -> None:
        super().__init__(f"{code}: {details}" if details else code)
        self.code = code
        self.details = details


@dataclass(frozen=True, slots=True)
class ProbeResult:
    confidence: float
    container_format_id: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RawRecordFrame:
    record_type: int
    record_version: int
    payload_length: int
    sequence: int
    timestamp_us: int
    valid_flags: int
    payload_bytes: bytes
    source_offset: int
    crc_valid: bool


@dataclass(slots=True)
class ParseOptions:
    diagnostics: ParserDiagnostics = field(default_factory=ParserDiagnostics)
    context: TaskContext = field(default_factory=TaskContext)
    source_size: int | None = None
    maximum_payload_length: int = 1_048_576
    maximum_resync_scan_bytes: int = 65_536
    maximum_resync_candidates: int = 1_024
    damaged_span_preview_bytes: int = 96


@dataclass(frozen=True, slots=True)
class LogContainerMetadata:
    plugin_id: str
    container_format_id: str
    version: str
    api_version: int
    display_name: str
    builtin: bool = False


class LogContainerPlugin(ABC):
    metadata: LogContainerMetadata

    @abstractmethod
    def probe(self, source: BinaryIO) -> ProbeResult:
        raise NotImplementedError

    @abstractmethod
    def header_read(
        self,
        source: BinaryIO,
        options: ParseOptions,
    ) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def iter_frames(
        self,
        source: BinaryIO,
        options: ParseOptions,
    ) -> Iterator[RawRecordFrame]:
        raise NotImplementedError
