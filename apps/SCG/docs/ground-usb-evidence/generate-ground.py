"""Software-only end-to-end validation; no device, serial or uploader access."""
from pathlib import Path
from dataclasses import replace
import sys, json, hashlib, shutil

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
SCG = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT.parent / "ground-usb-worktree/apps/SCG"
sys.path[:0] = [str(SCG / "src"), str(SCG / "tests")]
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from test_round2_targets import _GroundBoardProject_Get

service = FccgService(ROOT / "workspace")
catalog = PluginCatalog(SCG / "plugins/builtin", SCG / "plugins/installed")
catalog.Scan()
service.catalog = catalog
results = []
for name, mcu, pc in (("f103-usb", "stm32f103c8t6", "usb_cdc"),
                      ("f103-uart", "stm32f103c8t6", "uart"),
                      ("f407-usb", "stm32f407vet6", "usb_cdc")):
    model = _GroundBoardProject_Get(catalog)
    cube_root = ROOT / ("cube-" + name)
    package = Path("D:/Tools/Embedded/STM32/Repository") / ("STM32Cube_FW_F1_V1.8.7" if name.startswith("f103") else "STM32Cube_FW_F4_V1.28.3")
    # CubeMX copy-only omits package-level notices. Preserve the installed
    # official package terms in these disposable validation inputs; no vendor
    # implementation code is substituted or copied from SCG.
    for notice in ("License.md", "Package_license.md"):
        if (package / notice).is_file():
            shutil.copyfile(package / notice, cube_root / notice)
    usb_notice = package / "Middlewares/ST/STM32_USB_Device_Library/LICENSE.txt"
    if pc == "usb_cdc" and usb_notice.is_file():
        shutil.copyfile(usb_notice, cube_root / "USB_DEVICE/USB_Library_LICENSE.txt")
    imported = service.CubeMxProject_Import(ROOT / ("cube-" + name), model,
                                            risk_acknowledged=True, target="ground")
    hardware = imported.hardware
    resources = {r.resource_id: r for r in hardware.resources}
    nss = "SPI_RADIO_NSS" if "SPI_RADIO_NSS" in resources else "RADIO_NSS"
    assignments = {"radio0:radio_bus": "SPI1", "radio0:radio_nss": nss,
                   "radio0:radio_reset": "RADIO_RST", "radio0:radio_busy": "RADIO_BUSY",
                   "radio0:radio_dio1": "RADIO_DIO1", "radio0:time": "SYSTEM_TIME"}
    exact = catalog.Component_Get("silverstar.mcu." + mcu)
    model.ground_target = replace(model.ground_target, board="", mcu=exact.component_id,
        hardware=hardware, pc_interface=pc, pc_resource="USART1" if pc == "uart" else "",
        resource_assignments=assignments,
        baudrate=resources["USART1"].metadata["baud_rate"],
        build=replace(model.ground_target.build, target_profile=exact.platform.build_target_profile))
    issues = GroundTargetIssues_Get(model, catalog)
    if issues:
        raise RuntimeError(str(issues))
    output = ROOT / ("generated-" + name)
    ProjectRoot_Save(model, output)
    result = TargetGeneration_Apply(model, catalog, service.policy, output, TargetScope.GROUND)
    target = output / "Ground_Station"
    graph = json.loads((target / "Generated/ground_source_graph.json").read_text(encoding="utf8"))
    if any(p.startswith("Drivers/") for p in graph["sources"]):
        raise RuntimeError("A plugin-owned HAL source entered imported Ground")
    if not all(p.startswith("HardwareGenerated/") for p in (*graph["asm_sources"], graph["linker_script"])):
        raise RuntimeError("Startup/linker not owned by imported CubeMX project")
    if any((target / "Drivers").glob("**/*")):
        raise RuntimeError("A second Drivers tree was copied")
    results.append({"case": name, "target": str(target), "snapshot": hardware.snapshot_id,
                    "source_count": len(graph["sources"]), "hashes": result.file_hashes})
    print("GENERATED", name, len(graph["sources"]), target)
(ROOT / "generation-results.json").write_text(json.dumps(results, indent=2), encoding="utf8")
