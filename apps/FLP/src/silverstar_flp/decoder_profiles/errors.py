from __future__ import annotations


class DecoderProfileError(RuntimeError):
    def __init__(self, code: str, details: str = "") -> None:
        super().__init__(f"{code}: {details}" if details else code)
        self.code = code
        self.details = details


class RecordDecodeError(DecoderProfileError):
    pass
