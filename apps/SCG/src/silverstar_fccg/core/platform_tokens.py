"""Canonical tokens shared by platform matching and exact-domain admission."""
import re


def PlatformToken_Get(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())
