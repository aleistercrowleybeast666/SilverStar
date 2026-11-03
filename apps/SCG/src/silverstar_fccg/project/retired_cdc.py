"""Read-only recognition of historical MCU CDC projects and their imports."""
from pathlib import PurePosixPath


MIGRATION_NOTICE = (
    'MCU native USB CDC has been retired. Select Ground hardware, UART and its '
    'serial resource, verify the configured baud rate, then apply and save. '
    'For a CDC CubeMX source, generate and import a separate UART project.'
)


def NativeCdcHardware_Is(hardware) -> bool:
    facts = hardware.inventory
    return (any(key in facts for key in ('native_complete_classic_cdc', 'native_ground_backend',
                                         'usb_ground_c071_native'))
            or facts.get('usb_cdc') is True
            or any(resource.kind == 'usb_cdc' for resource in hardware.resources)
            or any(PurePosixPath(path.replace('\\', '/')).name.casefold() in
                   {'usbd_cdc.c', 'usbd_cdc_if.c'} for path in hardware.build_sources))


def NativeCdcMigration_Required(model) -> bool:
    return (model.native_usb is not None or model.ground_target.pc_interface == 'usb_cdc'
            or NativeCdcHardware_Is(model.ground_target.hardware))
