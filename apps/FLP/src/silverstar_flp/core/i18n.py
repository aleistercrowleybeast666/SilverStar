from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SUPPORTED_LANGUAGES = ("zh_CN", "en_US")


class Translator:
    def __init__(self, language: str = "zh_CN") -> None:
        self._catalogs: dict[str, dict[str, str]] = {}
        self.language = language if language in SUPPORTED_LANGUAGES else "zh_CN"

    def Language_Set(self, language: str) -> None:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language_unsupported:{language}")
        self.language = language

    def Text_Get(self, code: str, **values: Any) -> str:
        catalog = self._Catalog_Load(self.language)
        fallback = self._Catalog_Load("en_US")
        text = catalog.get(code, fallback.get(code, code))
        try:
            return text.format(**values)
        except (KeyError, ValueError):
            return text

    def _Catalog_Load(self, language: str) -> dict[str, str]:
        if language in self._catalogs:
            return self._catalogs[language]
        path = Path(__file__).resolve().parent.parent / "i18n" / f"{language}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            catalog = {str(key): str(value) for key, value in payload.items()}
        except (OSError, json.JSONDecodeError):
            catalog = {}
        self._catalogs[language] = catalog
        return catalog
