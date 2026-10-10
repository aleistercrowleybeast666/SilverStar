"""Exact mini native PCD input and separately owned classic CDC companion.

This is a bounded software profile, not general C0 or native CubeMX CDC support.
The input project is never edited and the companion contains no HAL/CMSIS,
startup or linker replacement.
"""
from pathlib import Path
import hashlib
import json
import difflib

PART = "STM32C071FBP6"
COMPANION = "silverstar.usb_cdc.stm32c071_mini"
PROFILE = "C071FBP6_MINI_USB_V1"
PREFIX = "HardwareGenerated/C071ClassicCDC/"
_EXPECTED = {
    "companion-manifest.json": "8835f4c76e6ea94ceeccf742ec59665157ddf2a089a4a361ad25b2671afcc6d7",
    "native-profile.json": "5c9ad2ccaae3b0bd4a81c00e5c450610f48c82b7d5958c9587b921be82d29589",
}


def C071Profile_Get(name: str) -> dict:
    if name not in _EXPECTED:
        raise ValueError("unknown C071 profile metadata")
    plugin = Path(__file__).resolve().parents[3] / "plugins/builtin/silverstar_usb_cdc_stm32c071_mini"
    path = plugin / name
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != _EXPECTED[name]:
        raise ValueError("C071 reviewed profile metadata changed: " + name)
    return json.loads(path.read_text(encoding="utf8"))


def C071Native_Validate(root: Path) -> dict:
    # Publish the effective CDC capability only after validating the actual
    # registered payload, rather than trusting a part number or manifest alone.
    from silverstar_fccg.plugins.manifest import PluginManifest_Load
    plugin = Path(__file__).resolve().parents[3] / "plugins/builtin/silverstar_usb_cdc_stm32c071_mini"
    C071Companion_Validate(PluginManifest_Load(plugin / "plugin.json"))
    profile = C071Profile_Get("native-profile.json")
    if hashlib.sha256((root / "Makefile").read_bytes()).hexdigest() != profile["makefile_sha256"]:
        raise ValueError("C071 native literal build inventory changed")
    iocs = tuple(root.glob("*.ioc"))
    if len(iocs) != 1 or hashlib.sha256(iocs[0].read_bytes()).hexdigest() != profile["ioc_sha256"]:
        raise ValueError("C071 requires the exact reviewed mini IOC profile; other parts/pins/configurations are unsupported")
    actual = {p.relative_to(root).as_posix() for directory in (root / "Core", root / "Drivers")
              for p in directory.rglob("*") if p.is_file()}
    if actual != set(profile["files_sha256"]):
        raise ValueError("C071 native Core/Drivers file inventory differs from reviewed complete input")
    for relative, digest in profile["files_sha256"].items():
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("C071 native dependency escapes input: " + relative)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("C071 native source/configuration changed: " + relative)
    for relative, key in (("startup_stm32c071xx.s", "startup_sha256"),
                          ("STM32C071XX_FLASH.ld", "linker_sha256")):
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != profile[key]:
            raise ValueError("C071 native startup/linker identity changed")
    manifest = C071Profile_Get("companion-manifest.json")
    return {"profile": PROFILE, "component": COMPANION, "version": "0.1.1",
            "manifest_sha256": _EXPECTED["companion-manifest.json"],
            "native_profile_sha256": _EXPECTED["native-profile.json"],
            "source_commits": manifest["source_commits"], "vendor_patches": manifest["vendor_patches"],
            "native_project_complete": True, "native_cdc": False,
            "input_kind": "native_pcd_plus_pinned_classic_cdc",
            "support_maturity": "experimental"}


# Package pad identity survives normalization of CubeMX's remapped names.
# PA9/PA10 share the USB pads; PB3..PB6 and PA14/PA15 are shared package pads.
C071_PAD_ALIASES = {
    "16": ("PA11", "PA9"), "17": ("PA12", "PA10"),
    "19": ("PA14", "PA15"), "20": ("PB3", "PB4", "PB5", "PB6"),
}


def C071PadIdentity_Get(ioc: str) -> dict:
    fields = dict(line.split("=", 1) for line in ioc.splitlines() if "=" in line)
    raw = {fields[key]: fields.get(fields[key] + ".Signal", "")
           for key in fields if key.startswith("Mcu.Pin") and key[7:].isdigit()}
    return {pad: {"aliases": list(aliases), "selected_raw": [name for name in raw
                if name in aliases or name.startswith((aliases[0] + " [", aliases[0] + "-"))],
                "normalized": aliases[0]} for pad, aliases in C071_PAD_ALIASES.items()}


def C071Companion_Validate(component) -> dict:
    if component.component_id != COMPANION or component.source != "builtin" or component.version != "0.1.1":
        raise ValueError("C071 companion must be its exact registered builtin revision")
    manifest = C071Profile_Get("companion-manifest.json")
    actual = {p.relative_to(component.payload_root).as_posix() for p in component.PayloadFiles_Get()}
    if actual != set(manifest["files_sha256"]):
        raise ValueError("C071 companion file inventory changed")
    for relative, digest in manifest["files_sha256"].items():
        path = component.payload_root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(component.payload_root.resolve()):
            raise ValueError("C071 companion dependency escapes payload")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("C071 companion source changed: " + relative)
    for patch in manifest["vendor_patches"]:
        original = component.payload_root / patch["original_path"]
        derived = component.payload_root / patch["derived_path"]
        expected = ''.join(difflib.unified_diff(
            original.read_text(encoding='utf8').splitlines(keepends=True),
            derived.read_text(encoding='utf8').splitlines(keepends=True),
            fromfile=patch["original_path"], tofile=patch["derived_path"]))
        if expected.encode() != (component.payload_root / patch["patch_path"]).read_bytes():
            raise ValueError("C071 companion patch is not reproducible: " + patch["id"])
        for field in ("original", "derived", "patch"):
            if manifest["files_sha256"][patch[field + "_path"]] != patch[field + "_sha256"]:
                raise ValueError("C071 companion patch provenance differs: " + patch["id"])
    return manifest


def C071GroundModel_Validate(model, catalog) -> None:
    from dataclasses import asdict
    from silverstar_fccg.project.model import GroundRadioConfigurations_Get
    ground = model.ground_target
    hardware = ground.hardware
    if (ground.mcu != "silverstar.mcu.stm32c071fbp6" or hardware.mcu != PART or
            hardware.mode != "custom" or ground.board or ground.pc_interface != "usb_cdc" or
            hardware.hal_cmsis_source_policy != "imported_tree_authoritative"):
        raise ValueError("C071 mini requires exact MCU, complete native custom input and USB CDC")
    radios = GroundRadioConfigurations_Get(ground)
    if (model.air_link.radio_family != "sx128x" or len(radios) != 1 or
            radios[0].plugin != "silverstar.device.telemetry.sx1281" or
            radios[0].module_variant != "e28_2g4m12sx" or radios[0].instance_id != "radio0"):
        raise ValueError("C071 mini requires its single reviewed E28 SX1281 radio")
    expected = {"radio0:" + role: value for role, value in {
        "radio_bus": "SPI1", "radio_nss": "RADIO_NSS", "radio_reset": "RADIO_RESET",
        "radio_busy": "RADIO_BUSY", "radio_dio1": "RADIO_DIO1", "time": "SYSTEM_TIME"}.items()}
    if ground.resource_assignments != expected:
        raise ValueError("C071 mini fixed radio/resource binding changed")
    companion = hardware.inventory.get("c071_companion", {})
    if (companion.get("profile") != PROFILE or companion.get("component") != COMPANION or companion.get("version") != "0.1.1" or
            companion.get("manifest_sha256") != _EXPECTED["companion-manifest.json"] or
            companion.get("native_profile_sha256") != _EXPECTED["native-profile.json"] or
            companion.get("native_cdc") is not False or
            companion.get("input_kind") != "native_pcd_plus_pinned_classic_cdc"):
        raise ValueError("C071 registered companion provenance missing or changed; reimport")
    profile = C071Profile_Get("native-profile.json")
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    ignore = {"ground_cubemx_base", "c071_companion", "package_pad_identity", "native_usb_cdc", "usb_cdc"}
    inventory = {k: v for k, v in hardware.inventory.items() if k not in ignore}
    if hardware.inventory.get("package_pad_identity") != profile["package_pad_identity"]:
        raise ValueError("C071 shared physical pad identity changed; reimport")
    if (digest([asdict(r) for r in hardware.resources]) != profile["resources_sha256"] or
            digest(inventory) != profile["native_inventory_sha256"]):
        raise ValueError("C071 native resource/pin/clock inventory changed; reimport")
    for name, value in profile["effective_build"].items():
        actual = getattr(hardware, name)
        if (list(actual) if isinstance(actual, tuple) else actual) != value:
            raise ValueError("C071 effective source ownership changed: " + name)
    hashes = hardware.inventory.get("ground_cubemx_base", {}).get("artifact_hashes", {})
    expected_hashes = dict(profile["files_sha256"])
    expected_hashes.update({"Makefile": profile["makefile_sha256"],
        hardware.ioc_file: profile["ioc_sha256"],
        "startup_stm32c071xx.s": profile["startup_sha256"],
        "STM32C071XX_FLASH.ld": profile["linker_sha256"]})
    if any(hashes.get(path) != digest for path, digest in expected_hashes.items()):
        raise ValueError("C071 stored native identity differs from reviewed complete input")
    C071Companion_Validate(catalog.Component_Get(COMPANION))
