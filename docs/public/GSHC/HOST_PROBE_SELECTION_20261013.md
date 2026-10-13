# GSHC 0.1.3 host probe selection

This development increment adds a host probe selector to the connection header.
It does not implement a debug session or an IDE backend. The frozen 0.1.2 tag,
release packages, firmware and flight algorithms are outside this change.

## Use

Run `.venv\Scripts\python.exe apps\GSHC\main.py` from the repository root.
The old packaged executable is unchanged. The header places ground and FC
maintenance serial controls at the left, then the **SWD probe** selector and
**Detect / Retry** button at the right. Groups wrap onto additional rows when
space is limited. Serial baud rates remain editable and independent. A probe
has no serial baud rate.

Startup performs one asynchronous host inventory. A single candidate can be
selected automatically. Multiple candidates require an explicit selection;
the selected item is keyed by its Windows USB parent instance ID, not its list
index. The full identity, interface metadata and host PnP status are available
in the tooltip. A location-derived identity may change when moved to another
USB port; it is labelled separately from a USB serial component.

Successful inventories repeat after 10 seconds. A disappeared selection is
cleared; another probe is never silently substituted, and reappearance requires
selection after that invalidation. Host enumeration failure also invalidates
the old selection. Retry remains available for no-device, dependency and error
states. An in-flight inventory disables repeated clicks and has a 20-second
deadline. Closing cancels the worker and waits for its completion before
destroying the window. Only that worker's own inventory helper can be stopped.

## Boundary and dependencies

The Windows backend uses an installed PowerShell (`pwsh.exe` preferred, Windows
PowerShell fallback), CIM `Win32_PnPEntity` present-device metadata and its
read-only `GetDeviceProperties` method. Windows 10 or later is required by that
method. Missing runtime/cmdlets and inventory failures have distinct states.
Nothing installs packages, changes drivers, resets hardware, or opens COM,
WinUSB, HID or SWD interfaces. Enumeration is on a worker thread, with at most
512 device nodes and 32 candidate probes accepted.

Microsoft documents the [PnP entity properties](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-pnpentity)
and [GetDeviceProperties](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/getdeviceproperties-win32-pnpentity).
No external source code or probe SDK was copied into this increment.

CMSIS-DAP/DAPLink, ST-Link and J-Link names are host descriptor candidates,
not verified protocol compatibility. Composite interfaces are grouped using
the actual OS parent chain; missing/ambiguous parent data fails the inventory
instead of inventing an identity. A serial-class interface alone never counts
as an SWD probe. DAPLink's COM role and debug role remain independent; a separate
USB-UART adapter and a separate probe are also valid choices.

“Probe selected” explicitly says **target not connected**. Host PnP “OK” does
not prove that a probe is free, that its driver can be opened, that the target
is powered, or that firmware is ready. Probe occupancy and target state remain
unknown. “Enumerating” describes this application's inventory work, not another
debugger's ownership. AIR M0 readiness and all command gates remain authoritative.

## Acceptance

1. Start the source GUI and find the SWD selector and rightmost retry button.
2. With zero candidates, verify the no-probe state. With one, verify its full
   identity and “target not connected”; with multiple, select explicitly.
3. Resize or change language: serial groups stay at the left and the probe
   group wraps while keeping its retry button visible.
4. When hardware is available for manual testing, remove the selected probe
   and wait for an inventory or press retry. Selection must clear. Replugging
   must not silently substitute a target. No interface-open step exists here.

Automated regressions simulate removal/replug, multiple probes, missing
dependencies, failures, repeated clicks and late completion during close.
Actual host inventory and Windows Qt layout observations, commands, source
hashes and remaining validation limits are recorded with this increment's
[evidence record](../../../apps/GSHC/docs/evidence/host_probe_20261013/README.md).
Simulated cases are not physical hotplug or target verification.
