from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import FlightDataset


class ParserError(RuntimeError):
    def __init__(self, code: str, details: str = "") -> None:
        super().__init__(f"{code}: {details}" if details else code)
        self.code = code
        self.details = details


@dataclass(frozen=True, slots=True)
class LogParserMetadata:
    plugin_id: str
    version: str
    display_name: str
    description: str
    supported_profiles: tuple[int, ...]


class LogParserPlugin(ABC):
    metadata: LogParserMetadata

    @abstractmethod
    def probe(self, path: Path) -> float:
        raise NotImplementedError

    @abstractmethod
    def parse(self, path: Path, context: TaskContext | None = None) -> FlightDataset:
        raise NotImplementedError
