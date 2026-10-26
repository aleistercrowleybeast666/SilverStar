"""Private exact C071 ordinary recipe; no formal release or review assertion.

Recipe provenance b66f142; independent USB safety review has no passed outcome.
"""
from __future__ import annotations
from silverstar_fccg.app.version import FirmwareIdentity_Resolve
from silverstar_fccg.generator.multi_target import (
    AirLinkHeader_Render,
    DeviceInstance,
    GROUND_CORE_ID,
    GROUND_DIRECTORY,
    GroundEnvironmentFiles_Render,
    GroundRadioAirHeader_Render,
    GroundRadioConfig_Render,
    GroundRadioConfigurations_Get,
    GroundTargetIssues_Get,
    PluginCatalog,
    ProjectModel,
    SourceGraph_Resolve,
    _InstanceResourcesSource_Render,
    _Main_Integrate,
    _Makefile_Render,
    _PayloadFiles_Add,
    _PcAdapter_Render,
    _PlatformResources_Render,
    _ResourceHeader_Render,
    _UsbCallback_Integrate,
    _UsbConf_Integrate,
    _UserSection_Insert,
    _VerifiedBoardMain_Prepare,
    __version__,
    json,
    replace
)

def _GroundModel_Get(model: ProjectModel, catalog: PluginCatalog) -> ProjectModel:
    ground = model.ground_target
    mcu_family = str(
        catalog.Component_Get(ground.mcu).metadata.get("platform_family_id", "")
    )
    if not mcu_family:
        raise ValueError("Ground exact MCU does not declare a family backend")
    return replace(
        model, core=GROUND_CORE_ID, mcu_family=mcu_family,
        mcu=ground.mcu, board=ground.board, os="",
        device_instances=[DeviceInstance(radio.instance_id, radio.plugin,
                          module_variant=radio.module_variant, tx_power_dbm=radio.tx_power_dbm)
                          for radio in GroundRadioConfigurations_Get(ground)],
        base_components=(["silverstar.usb_cdc.stm32c071_mini"]
                         if ground.hardware.mcu == "STM32C071FBP6" else []), strategies={}, modes={}, protocols={
            "telemetry": None, "maintenance": None, "logging": None,
        }, development_environment="", hardware=ground.hardware,
        resource_assignments=dict(ground.resource_assignments),
        capability_source_overrides={}, logging_streams=[],
        build=ground.build,
    )

def C071Recipe_Render(
    model: ProjectModel, catalog: PluginCatalog, native_files: dict[str, bytes],
) -> dict[str, bytes]:
    from silverstar_fccg.hardware.c071_mini import C071GroundModel_Validate
    C071GroundModel_Validate(model, catalog)
    issues = GroundTargetIssues_Get(model, catalog)
    if issues:
        raise ValueError("; ".join(f"{issue.code}: {issue.message}" for issue in issues))
    ground = model.ground_target
    ground_model = _GroundModel_Get(model, catalog)
    c071 = ground.hardware.mcu == "STM32C071FBP6"
    catalog = catalog.ProjectView_Get(ground_model)
    core = catalog.Component_Get(GROUND_CORE_ID)
    radio = catalog.Component_Get(ground.radio_plugin)
    mcu = catalog.Component_Get(ground.mcu)
    files: dict[str, bytes] = {}
    _PayloadFiles_Add(files, core)
    nrf24 = model.air_link.radio_family == "nrf24"
    backend_adapters = core.metadata.get("ground_radio_backends", {})
    if set(backend_adapters) != {"sx128x", "nrf24"}:
        raise ValueError("Ground core must declare both supported backend adapters")
    for path in backend_adapters.values():
        if not isinstance(path, str) or not path.startswith("Ground/Radio/Src/") or ".." in path.split("/") or path not in files:
            raise ValueError("Ground backend adapter must be an owned declared payload")
    radio_adapter = backend_adapters[model.air_link.radio_family]
    for backend, path in backend_adapters.items():
        if backend != model.air_link.radio_family:
            files.pop(path)
    _PayloadFiles_Add(files, radio, skip_adapter=True)
    family = catalog.Component_Get(ground_model.mcu_family)
    platform_api = catalog.Component_Get("silverstar.platform.api")
    for owner in (platform_api, family, mcu):
        for source in owner.PayloadFiles_Get():
            relative = source.relative_to(owner.payload_root).as_posix()
            if (ground.hardware.hal_cmsis_source_policy == "imported_tree_authoritative"
                    and (relative.startswith(("Drivers/", "Middlewares/"))
                         or relative in {mcu.build.linker_script, *mcu.build.asm_sources})):
                continue
            if relative.startswith(("Middlewares/Third_Party/FatFs/", "FATFS/")):
                continue
            if relative.startswith(("Platform/", "Drivers/", "BuildSystem/", "Middlewares/")) or relative in {
                mcu.build.linker_script, *mcu.build.asm_sources,
            }:
                files[relative] = source.read_bytes()
    flight_core = catalog.Component_Get(model.core)
    for relative in (
        "Common/Inc/silverstar_assert.h", "Common/Inc/silverstar_compiler.h",
        "Common/Src/silverstar_assert.c", "Interfaces/Inc/system_device_types.h",
        "Tools/check_power_of_ten.ps1",
    ):
        files[relative] = (flight_core.payload_root / relative).read_bytes()
    if ground.hardware.mode == "board_plugin":
        board = catalog.Component_Get(ground.board)
        for source in board.PayloadFiles_Get():
            relative = source.relative_to(board.payload_root).as_posix()
            if not relative.startswith("FATFS/"):
                files[relative] = source.read_bytes()
    else:
        files.update({"HardwareGenerated/STM32CubeMX/"+p:b for p,b in native_files.items()})

    main_path = "Core/Src/main.c" if ground.hardware.mode == "board_plugin" else \
        "HardwareGenerated/STM32CubeMX/Core/Src/main.c"
    if main_path not in files:
        raise ValueError("Ground CubeMX hardware has no generated Core/Src/main.c")
    if ground.hardware.mode == "board_plugin":
        files[main_path] = _VerifiedBoardMain_Prepare(
            files[main_path], catalog.Component_Get(ground.board)
        )
    replacements = {}
    if c071:
        from silverstar_fccg.generator.ground_c071_usb import C071Files_Integrate
        replacements = C071Files_Integrate(files,
            catalog.Component_Get("silverstar.usb_cdc.stm32c071_mini"),
            _UserSection_Insert, _UsbConf_Integrate)
        main_path = replacements[main_path]
        path = "Ground/Core/Src/ground_bridge.c"
        bridge = files[path].decode()
        site = "    GroundRadio_Process();"
        if bridge.count(site) != 1:
            raise ValueError("unreviewed C071 bridge service site")
        files[path] = ('#include "pc_c071_usb.h"\n' +
            bridge.replace(site, "    PcC071Usb_Service();\n" + site)).encode()
    else:
        files[main_path] = _Main_Integrate(files[main_path], usb=ground.pc_interface == "usb_cdc")
    if ground.pc_interface == "usb_cdc" and not c071:
        callback_paths = [path for path in files if path.endswith("/usbd_cdc_if.c")]
        if len(callback_paths) != 1:
            raise ValueError("Ground CubeMX hardware has no unique usbd_cdc_if.c")
        original_callback = files[callback_paths[0]]
        files[callback_paths[0]] = _UsbCallback_Integrate(original_callback)
        from silverstar_fccg.generator.ground_usb_control import NativeControl_Integrate, NativeControl_Definitions_Validate
        replacements.update(NativeControl_Integrate(files, callback_paths[0], original_callback))
        conf_paths = [path for path in files if path.endswith("/usbd_conf.c")]
        if len(conf_paths) != 1:
            raise ValueError("Ground CubeMX hardware has no unique usbd_conf.c")
        files[conf_paths[0]] = _UsbConf_Integrate(files[conf_paths[0]])

    files["Generated/Inc/project_resources.h"] = _ResourceHeader_Render(
        ground_model, catalog
    ).encode("utf-8")
    files["Generated/Src/project_resources.c"] = _InstanceResourcesSource_Render(
        ground_model, catalog
    ).encode("utf-8")
    files["Generated/Src/platform_resources.c"] = _PlatformResources_Render(
        ground_model, catalog
    ).encode("utf-8")
    files["Generated/Inc/ground_radio_config.h"] = GroundRadioConfig_Render(ground, model.air_link.protocol_profile).encode("utf-8")
    files["Generated/Inc/air_link_config.h"] = GroundRadioAirHeader_Render(
        ground, AirLinkHeader_Render(model, target="ground")).encode("utf-8")
    files["Generated/Src/pc_byte_stream.c"] = _PcAdapter_Render(model, family).encode("utf-8")

    base_graph = SourceGraph_Resolve(ground_model, catalog)
    sources = tuple(dict.fromkeys([
        *(replacements.get(source, source) for source in base_graph.sources
          if not source.startswith(("Generated/", "FATFS/", "Middlewares/Third_Party/FatFs/"))
          and "/Adapter/" not in source and (not nrf24 or source != backend_adapters["sx128x"])),
        *([radio_adapter] if nrf24 else []),
        "Common/Src/silverstar_assert.c", "Generated/Src/project_resources.c",
        "Generated/Src/platform_resources.c", "Generated/Src/pc_byte_stream.c",
        *(["Generated/Src/pc_usb_control.c"] if "Generated/Src/pc_usb_control.c" in files else []),
        main_path,
    ]))
    includes = tuple(dict.fromkeys([
        *(["Platform/STM32C0/Inc"] if c071 else []),
        *(path for path in base_graph.include_dirs
          if "/Adapter/" not in path and not path.startswith(("FATFS/", "Middlewares/Third_Party/FatFs/"))),
        "Generated/Inc", "Common/Inc", "Interfaces/Inc", "Platform/Inc",
    ]))
    defines = tuple(dict.fromkeys([
        "SILVERSTAR_AIR_LINK_ENABLED=1", *base_graph.defines,
        # Ground transfers bounded AIR frames; the established HAL option still
        # accommodates a full 255-byte radio payload plus its command header.
        "AIR_LINK_HAL_BUFFER_SIZE=260",
        *(["USE_HAL_PCD_REGISTER_CALLBACKS=0", "USBD_CLASS_BOS_ENABLED=0",
           "USBD_USER_REGISTER_CALLBACK=0"] if c071 else []),
    ]))
    if "Generated/usb_control_manifest.json" in files:
        NativeControl_Definitions_Validate(defines)
    if ground.hardware.hal_cmsis_source_policy == "imported_tree_authoritative":
        from silverstar_fccg.hardware.cubemx_ground import GroundEffectiveDefinitions_Validate
        GroundEffectiveDefinitions_Validate(defines, ground.hardware.mcu)
    missing_sources = [source for source in sources if source not in files]
    if missing_sources:
        raise ValueError("Ground source graph has missing files: " + ", ".join(missing_sources))
    required_irqs = ground.hardware.inventory.get("ground_cubemx_base", {}).get("required_irq_handlers", [])
    if ground.pc_interface == "usb_cdc":
        required_irqs = list(dict.fromkeys([*required_irqs,
            "USB_DRD_FS_IRQHandler" if c071 else
            "USB_LP_CAN1_RX0_IRQHandler" if family.component_id.endswith("stm32f1") else "OTG_FS_IRQHandler"]))
    graph = {
        "sources": sources, "asm_sources": base_graph.asm_sources,
        "include_dirs": includes, "defines": defines,
        "linker_script": base_graph.linker_script,
        "required_irq_handlers": required_irqs,
        "mcu_flags": base_graph.mcu_flags,
        "complete_cube_import": ground.hardware.hal_cmsis_source_policy == "imported_tree_authoritative" and not c071,
    }
    if "Generated/usb_control_manifest.json" in files:
        graph["usb_control_manifest"] = "Generated/usb_control_manifest.json"
        graph["vendor_patch_sources"] = [path for path in replacements.values()
                                         if path.startswith("HardwareGenerated/ReviewedUsbControl/")]
        graph["first_party_adapters"] = ["Generated/Src/pc_usb_control.c"]
    if c071:
        graph.update(registration_status="registered", support_maturity="experimental",
            input_kind="native_pcd_plus_pinned_classic_cdc", native_project_complete=True,
            native_cdc=False, pc_interface="usb_cdc", experimental_standalone_mcu="STM32C071FBP6",
            legacy_validation_profile={"field": "experimental_standalone_mcu",
                "purpose": "exact_reviewed_main_identity"},
            c071_companion=ground.hardware.inventory["c071_companion"],
            package_pad_identity=ground.hardware.inventory["package_pad_identity"],
            native_artifact_hashes=ground.hardware.inventory["ground_cubemx_base"]["artifact_hashes"],
            first_party_adapters=[path for path in replacements.values() if path.startswith("Platform/")],
            vendor_patch_sources=[path for path in replacements.values() if "/Reviewed/" in path],
            usb_power_profile={"self_powered": False, "declared_max_ma": 100,
                "suspend_status": "NOT PROVEN: power lifecycle and measured current"})
    files["Generated/ground_source_graph.json"] = (
        json.dumps(graph, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    files["Makefile"] = _Makefile_Render(
        sources, base_graph.asm_sources, includes, defines, base_graph,
        ground.build.toolchain_prefix or base_graph.toolchain_prefix,
    ).encode("utf-8")
    files[f"{GROUND_DIRECTORY}.code-workspace"] = (
        json.dumps({
            "folders": [{"path": "."}],
            "settings": {},
            "tasks": {
                "version": "2.0.0",
                "tasks": [{
                    "label": "Build Ground Station",
                    "type": "shell",
                    "command": ground.build.make_command,
                    "args": [],
                    "group": "build",
                }],
            },
        }, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    files.update(GroundEnvironmentFiles_Render(ground_model, catalog, base_graph, sources, includes, defines))
    hardware_fingerprint = ground.hardware.snapshot_id or ground.hardware.source_digest
    if ground.hardware.mode == "board_plugin" and not hardware_fingerprint:
        board_reference = catalog.Component_Get(ground.board).metadata.get("reference", {})
        hardware_fingerprint = str(
            board_reference.get("snapshot_digest") or
            catalog.Component_Get(ground.board).ManifestSha256_Get()
        )
    metadata = {
        "version_identity": FirmwareIdentity_Resolve(model.identity.firmware_version),
        "silverstar_version": __version__,
        "firmware_version": model.identity.firmware_version,
        "target_role": "ground_station",
        "air_profile": model.air_link.protocol_profile,
        "radio_module": ground.module_variant,
        "radio_family": model.air_link.radio_family,
        "frequency_hz": model.air_link.frequency_hz,
        "phy": {
            "mode": model.air_link.phy_mode,
            "spreading_factor": model.air_link.spreading_factor,
            "bandwidth_hz": model.air_link.bandwidth_hz,
            "coding_rate": model.air_link.coding_rate,
        },
        "pc_interface": ground.pc_interface,
        "hardware_fingerprint": hardware_fingerprint,
    }
    if nrf24:
        metadata["phy"] = {"mode": "esb", **model.air_link.nrf24,
            "physical_mtu": 32, "logical_mtu": model.air_link.packet_mtu,
            "fragment_version": 1, "metrics_supported": False}
    files["Generated/ground_target_metadata.json"] = (
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    return files
