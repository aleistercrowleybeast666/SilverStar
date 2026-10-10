"""Native import/model/render/build plumbing; formal firmware remains blocked.

Project metadata records a binding, never an authority or release approval.
Every candidate operation requires independent facts again and re-inspects the
immutable native snapshot. Candidate outputs are new, disjoint directories.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware.cubemx import CubeMxImportError, CubeMxImportResult, CubeMxImporter
from silverstar_fccg.hardware.native_classic_cdc import (
    NATIVE_CLASSIC_CDC_KEY, NATIVE_PREFIX, NativeClassicCdc_Import,
    NativeClassicCdc_Inspect, NativeDeviceFacts,
)
from silverstar_fccg.generator.native_ground import NativeGroundCandidate_Render
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import ProjectModel, ProjectModel_Load

BINDING_KEY = "native_ground_backend"
LIMITS = ("PRIVATE CANDIDATE ONLY; formal generation BLOCKED. NOT PROVEN: "
          "complete EP0/async lifecycle, manual critical contracts, whole-program "
          "stack/WCET and physical timing/hardware. F103 shared control ordinary integration only; independent USB safety review has no passed outcome. F407 shared EP0 repair not integrated.")
PROFILES = {
    "STM32F103C8T6": ("f103-systick-classic-v1", 72_000_000, "cortex-m3", ""),
    "STM32F407VET6": ("f407-tim1-indexed-v1", 168_000_000, "cortex-m4", "fpv4-sp-d16"),
}


class NativeGroundBackendResult(str, Enum):
    ImportedCandidate = "ImportedCandidate"
    RenderedCandidate = "RenderedCandidate"
    CompiledCandidate = "CompiledCandidate"
    FailedCandidate = "FailedCandidate"


@dataclass(frozen=True, slots=True)
class NativeGroundProjectImportResult:
    result: NativeGroundBackendResult
    model: ProjectModel
    imported: CubeMxImportResult
    profile: str


@dataclass(frozen=True, slots=True)
class NativeGroundCandidatePlan:
    model_sha256: str
    snapshot_id: str
    profile: str
    files: dict[str, bytes]
    graph: dict
    contract: dict


@dataclass(frozen=True, slots=True)
class NativeGroundCandidateOutputResult:
    result: NativeGroundBackendResult
    output: Path
    receipt: Path
    receipt_sha256: str
    detail: str = LIMITS


def _Json_Encode(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _Hash_Get(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _Profile_Get(facts: NativeDeviceFacts, hclk_hz: int) -> str:
    if not isinstance(facts, NativeDeviceFacts):
        raise CubeMxImportError("Trusted independent NativeDeviceFacts required")
    facts.Facts_Validate()
    profile = PROFILES.get(facts.part)
    if (profile is None or type(hclk_hz) is not int or
            (hclk_hz, facts.core, facts.fpu) != profile[1:]):
        raise CubeMxImportError("Unsupported native Ground device/clock profile; only exact F103/F407 candidates are implemented")
    return profile[0]


def _Resources_Get(model: ProjectModel, spi: str, gpio: tuple[str, ...]) -> dict[str, str]:
    if len(gpio) != 4:
        raise CubeMxImportError("Native Ground requires NSS/reset/busy/DIO1 role order")
    from silverstar_fccg.project.model import GroundRadioConfigurations_Get
    radios = GroundRadioConfigurations_Get(model.ground_target)
    if len(radios) != 1:
        raise CubeMxImportError("Native Ground currently requires one radio")
    identity = radios[0].instance_id
    return {identity + ":" + role: resource for role, resource in
            zip(("spi", "nss", "reset", "busy", "dio1"), (spi, *gpio))}


def NativeGroundProject_Import(importer: CubeMxImporter, catalog: PluginCatalog,
                              input_path: Path, model: ProjectModel, *,
                              device_facts: NativeDeviceFacts, spi_resource: str,
                              gpio_resources: tuple[str, ...], hclk_hz: int,
                              risk_acknowledged: bool) -> NativeGroundProjectImportResult:
    if risk_acknowledged is not True:
        raise CubeMxImportError("Explicit experimental native candidate acknowledgement required")
    profile = _Profile_Get(device_facts, hclk_hz)
    root, _ioc = importer._Input_Resolve(input_path)
    proof, inventory, native = NativeClassicCdc_Inspect(root, device_facts=device_facts,
        spi_resource=spi_resource, gpio_resources=gpio_resources)
    candidate = deepcopy(model)
    resources = _Resources_Get(candidate, spi_resource, gpio_resources)
    # Do not silently replace selected radio/protocol/LED policy. Existing renderer
    # validates those inputs before any native cache or project publication.
    NativeGroundCandidate_Render(native, proof, inventory, candidate, catalog, hclk_hz=hclk_hz)
    imported = NativeClassicCdc_Import(importer, input_path, device_facts=device_facts,
        spi_resource=spi_resource, gpio_resources=gpio_resources, risk_acknowledged=True)
    if imported.hardware.inventory[NATIVE_CLASSIC_CDC_KEY] != proof:
        raise CubeMxImportError("Native input changed during Ground import")
    binding = {"format_version": 1, "scope": "PRIVATE_NATIVE_GROUND_BACKEND",
               "profile": profile, "hclk_hz": hclk_hz,
               "facts_sha256": _Hash_Get(_Json_Encode(asdict(device_facts))),
               "snapshot_id": imported.hardware.snapshot_id,
               "spi": spi_resource, "gpio": list(gpio_resources),
               "formal_generation": "BLOCKED"}
    hardware = replace(imported.hardware, inventory={**deepcopy(imported.hardware.inventory), BINDING_KEY: binding})
    candidate.ground_target = replace(candidate.ground_target, mcu="", board="",
        hardware=hardware, resource_assignments=resources, pc_resource="")
    # Round-trip through the actual model parser before returning anything to save.
    from silverstar_fccg.project.model import ProjectModel_Parse
    candidate = ProjectModel_Parse(candidate.Dictionary_Get())
    return NativeGroundProjectImportResult(NativeGroundBackendResult.ImportedCandidate,
        candidate, imported, profile)


def _Snapshot_Inspect(importer: CubeMxImporter, model: ProjectModel, facts: NativeDeviceFacts):
    hardware = model.ground_target.hardware
    binding = hardware.inventory.get(BINDING_KEY)
    expected = {"format_version", "scope", "profile", "hclk_hz", "facts_sha256",
                "snapshot_id", "spi", "gpio", "formal_generation"}
    if not isinstance(binding, dict) or set(binding) != expected:
        raise CubeMxImportError("Native Ground backend binding is missing or unsupported")
    profile = _Profile_Get(facts, binding["hclk_hz"])
    if (type(binding["format_version"]) is not int or binding["format_version"] != 1 or
            binding["scope"] != "PRIVATE_NATIVE_GROUND_BACKEND" or
            binding["formal_generation"] != "BLOCKED" or binding["profile"] != profile or
            binding["facts_sha256"] != _Hash_Get(_Json_Encode(asdict(facts)))):
        raise CubeMxImportError("Native Ground binding differs from trusted facts/profile")
    identity = hardware.snapshot_id
    if (not re.fullmatch(r"[0-9a-f]{64}", identity) or
            identity != hardware.source_digest or identity != binding["snapshot_id"] or
            hardware.mode != "custom" or hardware.source_kind != "manual_import" or
            hardware.hal_cmsis_source_policy != "imported_tree_authoritative" or
            hardware.mcu != facts.part or hardware.risk_acknowledged is not True):
        raise CubeMxImportError("Native Ground hardware binding is inconsistent")
    if (not isinstance(binding["spi"], str) or not isinstance(binding["gpio"], list) or
            any(not isinstance(value, str) for value in binding["gpio"])):
        raise CubeMxImportError("Native Ground resource binding is invalid")
    if (model.ground_target.mcu or model.ground_target.board or model.ground_target.pc_resource or
            model.ground_target.resource_assignments !=
            _Resources_Get(model, binding["spi"], tuple(binding["gpio"]))):
        raise CubeMxImportError("Native Ground resources require explicit re-import/rebinding")
    snapshot = importer.policy.Path_Resolve(importer.cache_root / identity / "NativeClassicCdc", allow_root=False)
    if not snapshot.is_dir():
        raise CubeMxImportError("Native Ground snapshot unavailable; import in this backend workspace first")
    proof, inventory, native = NativeClassicCdc_Inspect(snapshot, device_facts=facts,
        spi_resource=binding["spi"], gpio_resources=tuple(binding["gpio"]))
    encoded = _Json_Encode(proof)
    # Native import digest uses default ensure_ascii=True; current facts strings
    # may contain non-ASCII provenance, so use its exact canonical encoding.
    native_encoded = json.dumps(proof, sort_keys=True, separators=(",", ":")).encode("utf-8")
    contract_path = importer.policy.Path_Resolve(snapshot.parent / "native-contract.json", allow_root=False)
    if (_Hash_Get(native_encoded) != identity or not contract_path.is_file() or
            contract_path.read_bytes() != native_encoded or
            _Json_Encode(hardware.inventory.get(NATIVE_CLASSIC_CDC_KEY)) != encoded):
        raise CubeMxImportError("Immutable native snapshot/contract or project proof is modified")
    build = proof["build"]
    if (hardware.build_sources != tuple(NATIVE_PREFIX + p for p in build["sources"]) or
            hardware.asm_sources != tuple(NATIVE_PREFIX + p for p in build["asm_sources"]) or
            hardware.include_dirs != tuple(NATIVE_PREFIX + p for p in build["include_dirs"]) or
            hardware.defines != tuple(sorted(build["defines"])) or
            hardware.linker_script != NATIVE_PREFIX + build["linker_script"]):
        raise CubeMxImportError("Native Ground source ownership inventory differs from snapshot")
    return snapshot, proof, inventory, native, binding


def NativeGroundCandidate_Plan(importer: CubeMxImporter, catalog: PluginCatalog,
                               model: ProjectModel, *, device_facts: NativeDeviceFacts) -> NativeGroundCandidatePlan:
    _snapshot, proof, inventory, native, binding = _Snapshot_Inspect(importer, model, device_facts)
    files, graph, contract = NativeGroundCandidate_Render(native, proof, inventory, model,
        catalog, hclk_hz=binding["hclk_hz"])
    files = {**{NATIVE_PREFIX + p: b for p, b in native.items()}, **files}
    files["candidate_config.ssproject"] = json.dumps(model.Dictionary_Get(), ensure_ascii=False, indent=2).encode("utf-8")
    files["Generated/native_ground_backend_binding.json"] = _Json_Encode(binding)
    return NativeGroundCandidatePlan(_Hash_Get(_Json_Encode(model.Dictionary_Get())),
        model.ground_target.hardware.snapshot_id, binding["profile"], files, graph, contract)


def _Output_Validate(importer: CubeMxImporter, model: ProjectModel, output: Path, project_root: Path | None = None) -> Path:
    path = output.absolute()
    if path.exists() or path.resolve() != path or path == Path(path.anchor):
        raise CubeMxImportError("Native candidate requires a new unaliased output directory")
    snapshot = importer.policy.Path_Resolve(importer.cache_root / model.ground_target.hardware.snapshot_id)
    protected = [snapshot, importer.cache_root]
    if project_root is not None:
        protected.append(project_root.resolve())
    if any(path.is_relative_to(root) or root.is_relative_to(path) for root in protected):
        raise CubeMxImportError("Native candidate output must be disjoint from project and imported cache")
    return path


def _Receipt_Write(output: Path, data: dict) -> Path:
    policy = WorkspacePolicy(output)
    return policy.Text_AtomicWrite("backend-receipt.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def NativeGroundCandidate_Export(importer: CubeMxImporter, catalog: PluginCatalog,
                                 model: ProjectModel, output: Path, *,
                                 device_facts: NativeDeviceFacts, task_context=None) -> NativeGroundCandidateOutputResult:
    plan = NativeGroundCandidate_Plan(importer, catalog, model, device_facts=device_facts)
    destination = _Output_Validate(importer, model, output)
    for path in plan.files:
        WorkspacePolicy(destination).RelativePath_Validate(path)
        if os.name == "nt" and len(str(destination / path)) >= 248:
            raise CubeMxImportError("Native candidate output paths exceed portable Windows limit")
    destination.mkdir(parents=True)
    policy = WorkspacePolicy(destination)
    try:
        for index, (path, content) in enumerate(plan.files.items(), 1):
            if task_context is not None:
                task_context.Cancel_RaiseIfRequested()
            policy.Bytes_AtomicWrite(path, content)
            if task_context is not None:
                task_context.Progress_Report(0.1 + 0.8 * index / len(plan.files), 'status.generation_running')
        _Snapshot_Inspect(importer, model, device_facts)
        if _Hash_Get(_Json_Encode(model.Dictionary_Get())) != plan.model_sha256:
            raise CubeMxImportError("Native model changed during candidate render")
        # Publication remains experimental even if every rendered byte is present.
        data = {"format_version": 1, "status": "RENDERED_NOT_COMPILED",
                "scope": "PRIVATE_NATIVE_GROUND_BACKEND", "model_sha256": plan.model_sha256,
                "snapshot_id": plan.snapshot_id, "profile": plan.profile,
                "files_sha256": {p: _Hash_Get(b) for p, b in plan.files.items()},
                "finished_utc": datetime.now(timezone.utc).isoformat(), "limits": LIMITS}
        receipt = _Receipt_Write(destination, data)
    except Exception as error:
        _Receipt_Write(destination, {"status": "FAILED_RENDER", "failure": str(error), "limits": LIMITS})
        raise
    return NativeGroundCandidateOutputResult(NativeGroundBackendResult.RenderedCandidate,
        destination, receipt, _Hash_Get(receipt.read_bytes()))


def NativeGroundCandidate_Build(importer: CubeMxImporter, catalog: PluginCatalog,
                                model: ProjectModel, project_root: Path, output: Path, *,
                                device_facts: NativeDeviceFacts, task_context=None) -> NativeGroundCandidateOutputResult:
    saved = ProjectModel_Load(project_root / "SilverStar.ssproject")
    if _Json_Encode(saved.Dictionary_Get()) != _Json_Encode(model.Dictionary_Get()):
        raise CubeMxImportError("Save the exact bound native project before candidate build")
    snapshot, _proof, _inventory, _native, binding = _Snapshot_Inspect(importer, saved, device_facts)
    plan = NativeGroundCandidate_Plan(importer, catalog, saved, device_facts=device_facts)
    destination = _Output_Validate(importer, saved, output, project_root)
    # The compiler owns a fresh output only. It receives facts from the trusted
    # caller, not from a project-controlled descriptor or receipt.
    from silverstar_fccg.build.native_compile import NativeCompile_Run
    args = SimpleNamespace(input=snapshot, device_facts=None, output=destination,
        spi=binding["spi"], gpio=binding["gpio"], clock_hz=binding["hclk_hz"],
        runtime_project=project_root / "SilverStar.ssproject",
        toolchain_prefix=saved.ground_target.build.toolchain_prefix,
        reviewed_hal=False, native_timer_probe=False, task_context=task_context)
    owner_token = secrets.token_hex(16)
    args.backend_owner_token = owner_token
    started = datetime.now(timezone.utc).isoformat()
    failure = None
    try:
        NativeCompile_Run(args, device_facts=device_facts, runtime_catalog=catalog)
        compilation = json.loads((destination / 'receipt.json').read_text(encoding='utf-8'))
        if (compilation.get('status') != 'NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED' or
                compilation.get('validation_scope') != 'PRIVATE_NATIVE_GROUND_RUNTIME_CANDIDATE' or
                compilation.get('runtime_model_sha256') != plan.model_sha256):
            raise CubeMxImportError("Native compiler did not produce a successful exact-model receipt")
        _Snapshot_Inspect(importer, saved, device_facts)
        if _Json_Encode(ProjectModel_Load(args.runtime_project).Dictionary_Get()) != _Json_Encode(saved.Dictionary_Get()):
            raise CubeMxImportError("Saved native project changed during candidate build")
        result = NativeGroundBackendResult.CompiledCandidate
    except Exception as error:
        failure = str(error)
        result = NativeGroundBackendResult.FailedCandidate
        owner = destination / 'backend-owner.json'
        if (not destination.is_dir() or not owner.is_file() or
                json.loads(owner.read_text(encoding='utf-8')).get('token') != owner_token):
            raise
    compile_receipt = destination / "receipt.json"
    data = {"format_version": 1, "status": result.value, "scope": "PRIVATE_NATIVE_GROUND_BACKEND",
            "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
            "model_sha256": plan.model_sha256, "project_root": str(project_root.resolve()),
            "snapshot_id": plan.snapshot_id, "profile": plan.profile,
            "compile_receipt_sha256": _Hash_Get(compile_receipt.read_bytes()) if compile_receipt.is_file() else None,
            "binding": binding, "failure": failure, "limits": LIMITS}
    receipt = _Receipt_Write(destination, data)
    if task_context is not None:
        task_context.Cancel_RaiseIfRequested()
    return NativeGroundCandidateOutputResult(result, destination, receipt,
        _Hash_Get(receipt.read_bytes()), failure or LIMITS)
