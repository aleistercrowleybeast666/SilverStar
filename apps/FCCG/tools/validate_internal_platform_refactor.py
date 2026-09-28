from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = WORKSPACE_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from silverstar_fccg.app.service import FccgService  # noqa: E402
from silverstar_fccg.generator.log_decoder_profile import (  # noqa: E402
    LogDecoderPackage_Verify,
)
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve  # noqa: E402


def Acceptance_Run(output_root: Path) -> dict[str, object]:
    tests_root = (WORKSPACE_ROOT / "tests").resolve()
    selected_root = output_root.resolve(strict=False)
    try:
        selected_root.relative_to(tests_root)
    except ValueError as error:
        raise ValueError("Acceptance output must remain below tests/") from error
    if selected_root.exists() and any(selected_root.iterdir()):
        raise ValueError(f"Acceptance output is not empty: {selected_root}")

    service = FccgService(WORKSPACE_ROOT)
    model = service.ReferenceProject_Create(
        "SilverStar_Internal_Platform_Acceptance"
    )
    first = service.Project_Save(model, selected_root)
    ready_after_generate = service.ProjectReadiness_Get(model, selected_root)

    loaded = service.Project_Open(selected_root)
    ready_after_reload = service.ProjectReadiness_Get(loaded, selected_root)
    second_plan = service.GenerationPlan_Create(loaded, selected_root)
    operation_counts = Counter(
        operation.operation for operation in second_plan.operations
    )
    second = service.GenerationPlan_Apply(loaded, second_plan)
    ready_after_second = service.ProjectReadiness_Get(loaded, selected_root)

    decoder_path = selected_root / loaded.log_decoder_profile.relative_path
    decoder_content = decoder_path.read_bytes()
    decoder_manifest = LogDecoderPackage_Verify(decoder_content)
    graph = SourceGraph_Resolve(loaded, service.catalog)
    return {
        "root": str(selected_root),
        "first": {
            "added": first.files_added,
            "modified": first.files_modified,
            "preserved": first.component_files_preserved,
        },
        "ready_after_generate": ready_after_generate.ready,
        "ready_after_reload": ready_after_reload.ready,
        "second_plan": dict(sorted(operation_counts.items())),
        "second": {
            "added": second.files_added,
            "modified": second.files_modified,
            "preserved": second.component_files_preserved,
        },
        "ready_after_second": ready_after_second.ready,
        "files_before_build": sum(
            1 for path in selected_root.rglob("*") if path.is_file()
        ),
        "source_count": len(graph.sources),
        "optional_platform_sources": [
            source
            for source in graph.sources
            if any(
                token in source
                for token in (
                    "platform_i2c_stm32f4.c",
                    "platform_can_stm32f4.c",
                    "platform_pwm_stm32f4.c",
                    "stm32f4xx_hal_i2c.c",
                    "stm32f4xx_hal_i2c_ex.c",
                    "stm32f4xx_hal_can.c",
                )
            )
        ],
        "decoder_bytes": len(decoder_content),
        "decoder_sha256": hashlib.sha256(decoder_content).hexdigest(),
        "decoder_protocols": sorted(decoder_manifest["protocols"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and verify the internal Platform refactor acceptance project"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            WORKSPACE_ROOT
            / "tests"
            / "acceptance_internal_firmware_plugin_refactor_20260829"
        ),
    )
    arguments = parser.parse_args()
    result = Acceptance_Run(arguments.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
