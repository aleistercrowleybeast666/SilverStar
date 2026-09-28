from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass

from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.hardware.inventory import HardwareInventory
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.plugins.manifest import PlatformMatchRule, PluginManifest


class PlatformMatchError(FccgError):
    pass


@dataclass(frozen=True, slots=True)
class DetectedMcuFacts:
    vendor: str
    part: str
    family: str
    package: str
    core: str
    provider: str

    def Dictionary_Get(self) -> dict[str, str]:
        return {
            "vendor": self.vendor,
            "mcu_part": self.part,
            "mcu_family": self.family,
            "package": self.package,
            "core": self.core,
            "provider": self.provider,
        }


@dataclass(frozen=True, slots=True)
class PlatformCandidate:
    component_id: str
    version: str
    rule: PlatformMatchRule
    exact: bool
    reason: str

    @property
    def Rank_Get(self) -> tuple[int, int, int]:
        return (
            1 if self.exact else 0,
            self.rule.priority,
            self.rule.specificity,
        )


@dataclass(frozen=True, slots=True)
class PlatformMatchResult:
    facts: DetectedMcuFacts
    selected: PlatformCandidate
    candidates: tuple[PlatformCandidate, ...]


def PlatformCompatibilityErrors_Get(
    manifest: PluginManifest,
    *,
    cubemx_version: str,
    firmware_package: str,
    source_policy: str = "",
) -> tuple[str, ...]:
    platform = manifest.platform
    if platform is None:
        return (f"{manifest.component_id} has no Platform compatibility contract",)
    contract = platform.compatibility
    errors: list[str] = []
    if not cubemx_version:
        errors.append(
            f"CubeMX version is missing; {manifest.component_id} requires "
            + ", ".join(contract.cubemx_versions)
        )
    elif cubemx_version not in contract.cubemx_versions:
        errors.append(
            f"CubeMX version mismatch for {manifest.component_id}: detected "
            f"{cubemx_version}, required "
            + ", ".join(contract.cubemx_versions)
        )
    if not firmware_package:
        errors.append(
            f"STM32Cube firmware package is missing; {manifest.component_id} requires "
            + ", ".join(contract.firmware_packages)
        )
    elif firmware_package not in contract.firmware_packages:
        errors.append(
            f"STM32Cube firmware package mismatch for {manifest.component_id}: "
            f"detected {firmware_package}, required "
            + ", ".join(contract.firmware_packages)
        )
    if source_policy and source_policy != contract.source_policy:
        errors.append(
            f"HAL/CMSIS source policy mismatch for {manifest.component_id}: "
            f"project uses {source_policy}, Platform requires {contract.source_policy}"
        )
    return tuple(errors)


def DetectedMcuFacts_FromInventory(
    inventory: HardwareInventory,
    *,
    vendor: str,
    provider: str,
) -> DetectedMcuFacts:
    return DetectedMcuFacts(
        vendor=vendor,
        part=inventory.mcu_part,
        family=inventory.mcu_family,
        package=inventory.package,
        core=inventory.core,
        provider=provider,
    )


def _Token_Get(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _Pattern_Get(value: str) -> str:
    return re.sub(r"[^A-Z0-9*?]", "", value.upper())


def _Pattern_Matches(pattern: str, value: str) -> bool:
    if not pattern:
        return True
    return fnmatch.fnmatchcase(_Token_Get(value), _Pattern_Get(pattern))


def _RuleCandidate_Get(
    manifest: PluginManifest,
    rule: PlatformMatchRule,
    facts: DetectedMcuFacts,
) -> PlatformCandidate | None:
    platform = manifest.platform
    if platform is None or platform.provider != facts.provider:
        return None
    if _Token_Get(rule.vendor) != _Token_Get(facts.vendor):
        return None
    exact = bool(rule.exact_part) and (
        _Token_Get(rule.exact_part) == _Token_Get(facts.part)
    )
    if rule.exact_part and not exact:
        return None
    if not rule.exact_part and not _Pattern_Matches(
        rule.family_pattern, facts.family or facts.part
    ):
        return None
    if rule.package_pattern and not _Pattern_Matches(
        rule.package_pattern, facts.package
    ):
        return None
    if rule.core_pattern and not _Pattern_Matches(rule.core_pattern, facts.core):
        return None
    match_kind = "exact part" if exact else "family pattern"
    return PlatformCandidate(
        component_id=manifest.component_id,
        version=manifest.version,
        rule=rule,
        exact=exact,
        reason=(
            f"{match_kind}; provider={facts.provider}; priority={rule.priority}; "
            f"specificity={rule.specificity}; verification={rule.verification}"
        ),
    )


def PlatformMatch_Resolve(
    facts: DetectedMcuFacts, catalog: PluginCatalog
) -> PlatformMatchResult:
    if not facts.part:
        raise PlatformMatchError("CubeMX inventory does not declare an exact MCU part")
    candidates: list[PlatformCandidate] = []
    for manifest in catalog.Type_Get("mcu"):
        if manifest.platform is None:
            continue
        for rule in manifest.platform.match_rules:
            candidate = _RuleCandidate_Get(manifest, rule, facts)
            if candidate is not None:
                candidates.append(candidate)
    if not candidates:
        raise PlatformMatchError(
            f"Detected {facts.part}, but no compatible MCU/Platform plugin is installed"
        )
    candidates.sort(
        key=lambda candidate: (
            candidate.Rank_Get,
            candidate.component_id,
            candidate.version,
        ),
        reverse=True,
    )
    best_rank = candidates[0].Rank_Get
    best = [candidate for candidate in candidates if candidate.Rank_Get == best_rank]
    unique_components = sorted({candidate.component_id for candidate in best})
    if len(unique_components) != 1:
        raise PlatformMatchError(
            f"MCU/Platform match for {facts.part} is ambiguous: "
            + ", ".join(unique_components)
        )
    selected = next(
        candidate
        for candidate in best
        if candidate.component_id == unique_components[0]
    )
    return PlatformMatchResult(facts, selected, tuple(candidates))
