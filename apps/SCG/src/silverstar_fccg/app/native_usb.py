"""SCG's separately derived, experimental native USB project workflow."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from silverstar_fccg.app.usb_transport import (
    UsbTransport_Export,
    UsbTransport_Plan,
    UsbTransportPlan,
    UsbTransportPlanResult,
)
from silverstar_fccg.build.native_usb import (
    NativeUsbBuild_Run,
    NativeUsbCompiler_Resolve,
)
from silverstar_fccg.core.task import TaskContext
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.native_usb_graph import (
    NativeUsbDigest_Get,
    NativeUsbGraph_Resolve,
    NativeUsbJson_Read,
    NativeUsbKit_Verify,
)
from silverstar_fccg.project.native_usb import (
    NativeUsbReference,
    NativeUsbReference_Parse,
)


class NativeUsbWorkflowResult(str, Enum):
    Rejected = "Rejected"
    Experimental = "Experimental"
    Prepared = "Prepared"
    Compiled = "Compiled"
    Diagnostics = "Diagnostics"


@dataclass(frozen=True, slots=True)
class NativeUsbWorkflow:
    result: NativeUsbWorkflowResult
    plan: UsbTransportPlan
    reference: NativeUsbReference | None
    receipt: dict | None = None


def NativeUsb_Inspect(native: Path, context: TaskContext) -> NativeUsbWorkflow:
    context.Cancel_RaiseIfRequested()
    plan = UsbTransport_Plan(native)
    context.Cancel_RaiseIfRequested()
    if plan.result == UsbTransportPlanResult.Rejected:
        return NativeUsbWorkflow(NativeUsbWorkflowResult.Rejected, plan, None)
    reference = NativeUsbReference(str(native.resolve()), NativeUsbDigest_Get(plan.files_sha256))
    return NativeUsbWorkflow(NativeUsbWorkflowResult.Experimental, plan, reference)


def _Reference_Verify(reference: NativeUsbReference, context: TaskContext) -> UsbTransportPlan:
    NativeUsbReference_Parse(reference.Dictionary_Get())
    inspected = NativeUsb_Inspect(Path(reference.native_root), context)
    if inspected.reference is None or inspected.reference.source_sha256 != reference.source_sha256:
        raise ValueError("Native USB input changed or is no longer eligible; inspect it again")
    return inspected.plan


def NativeUsb_Prepare(reference: NativeUsbReference, output: Path, context: TaskContext) -> NativeUsbWorkflow:
    plan = _Reference_Verify(reference, context)
    if plan.capabilities["automatic_integration"]["status"] != "SOURCE_SHAPE_AVAILABLE":
        raise ValueError("Native USB requires manually reviewed lifecycle hooks; automatic derivation unavailable")
    # Export reserves a new, disjoint directory; native user files are never replaced.
    UsbTransport_Export(reference.native_root, output, integrate=True)
    context.Cancel_RaiseIfRequested()
    output = output.resolve()
    graph = NativeUsbGraph_Resolve(plan, Path(reference.native_root), output)
    _Reference_Verify(reference, context)
    graph_path = output / "native-usb-source-graph.json"
    with graph_path.open("x", encoding="utf8") as stream:
        json.dump(graph, stream, indent=2)
    bound = replace(reference, output_root=str(output),
        kit_sha256=hashlib.sha256((output / "kit-sha256.json").read_bytes()).hexdigest(),
        graph_sha256=hashlib.sha256(graph_path.read_bytes()).hexdigest(), receipt_file="", receipt_sha256="")
    return NativeUsbWorkflow(NativeUsbWorkflowResult.Prepared, plan, bound)


def _Output_Verify(reference: NativeUsbReference, plan: UsbTransportPlan) -> dict:
    if not reference.output_root:
        raise ValueError("Prepare a separate native USB project before building")
    output = Path(reference.output_root)
    if output.is_symlink() or output.is_junction():
        raise ValueError("Native USB output cannot be an alias")
    policy = WorkspacePolicy(output)
    NativeUsbKit_Verify(output, reference.kit_sha256)
    path = policy.Path_Resolve(output / "native-usb-source-graph.json")
    if hashlib.sha256(path.read_bytes()).hexdigest() != reference.graph_sha256:
        raise ValueError("Native USB graph changed; regenerate to a new directory")
    graph = NativeUsbJson_Read(path)
    if graph != NativeUsbGraph_Resolve(plan, Path(reference.native_root), output):
        raise ValueError("Native USB graph no longer matches its input and source replacements")
    return graph


def NativeUsb_Build(reference: NativeUsbReference, compiler: str, context: TaskContext,
                    *, analyzer: bool = False) -> NativeUsbWorkflow:
    plan = _Reference_Verify(reference, context)
    graph = _Output_Verify(reference, plan)
    resolved = NativeUsbCompiler_Resolve(compiler)
    output = Path(reference.output_root)
    def verify():
        _Output_Verify(reference, _Reference_Verify(reference, context))
    receipt_path, receipt = NativeUsbBuild_Run(graph, output, resolved, context,
        analyzer=analyzer, verify_inputs=verify)
    bound = replace(reference, receipt_file=receipt_path.relative_to(output).as_posix(),
        receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest())
    result = (NativeUsbWorkflowResult.Diagnostics if receipt["status"] == "COMPILED_WITH_DIAGNOSTICS"
              else NativeUsbWorkflowResult.Compiled)
    return NativeUsbWorkflow(result, plan, bound, receipt)


def NativeUsb_Refresh(reference: NativeUsbReference, context: TaskContext) -> NativeUsbWorkflow:
    """Saved receipts are rechecked on demand, never replayed as admission."""
    plan = _Reference_Verify(reference, context)
    if not reference.output_root:
        return NativeUsbWorkflow(NativeUsbWorkflowResult.Experimental, plan, reference)
    graph = _Output_Verify(reference, plan)
    receipt = None
    if reference.receipt_file:
        policy = WorkspacePolicy(Path(reference.output_root))
        path = policy.Path_Resolve(Path(reference.output_root) / reference.receipt_file)
        if hashlib.sha256(path.read_bytes()).hexdigest() != reference.receipt_sha256:
            raise ValueError("Native USB receipt changed")
        receipt = NativeUsbJson_Read(path)
        elf = policy.Path_Resolve(Path(receipt["elf"]))
        if hashlib.sha256(elf.read_bytes()).hexdigest() != receipt["elf_sha256"]:
            raise ValueError("Native USB linked artifact changed")
        if receipt["source_sha256"] != reference.source_sha256:
            raise ValueError("Native USB receipt belongs to another input")
        if receipt["graph_digest"] != NativeUsbDigest_Get(graph):
            raise ValueError("Native USB receipt belongs to another source graph")
    # Revalidation does not execute compilers, rerun gates or grant a PASS.
    return NativeUsbWorkflow(NativeUsbWorkflowResult.Prepared, plan, reference, receipt)
