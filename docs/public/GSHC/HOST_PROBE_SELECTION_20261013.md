# GSHC 0.1.3 host probe selection

This development increment adds a host probe selector to the connection header.
The original increment did not implement a debug session or an IDE backend.
The subsequent [SWD read-only groundwork](SWD_READ_ONLY_20261013.md) adds the API,
CLI and explicit Maintenance-page controls; its original live admission was blocked.
The current [pyOCD/Horco adapter and bench results](SWD_PYOCD_BENCH_20261014.md)
record the subsequent bounded read-only connection. Discovery alone never connects a target.
The frozen 0.1.2 tag,
release packages, firmware and flight algorithms are outside this change.

## Use

Run `.venv\Scripts\python.exe apps\GSHC\main.py` from the repository root.
The old packaged executable is unchanged. The header places ground and FC
maintenance serial controls at the left, then the **SWD probe** selector,
**重新检测 / Detect Again** button and status text to its right. Controls on the
same row share a vertical center; compact groups wrap onto additional rows when
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

“Probe selected” explicitly says **no SWD session**. Host PnP “OK” does
not prove that a probe is free, that its driver can be opened, that the target
is powered, or that firmware is ready. Probe occupancy and target state remain
unknown. “Enumerating” describes this application's inventory work, not another
debugger's ownership. AIR M0 readiness and all command gates remain authoritative.

## Acceptance

1. Restart the source GUI and find the SWD selector and **重新检测** button.
2. With zero candidates, verify the no-probe state. With one, verify its full
   identity and “SWD 未连接”; with multiple, select explicitly.
3. Resize or change language: controls on a shared row stay level, status text
   sits to the right of its probe controls, and all groups remain visible when wrapping.
4. When hardware is available for manual testing, remove the selected probe
   and wait for an inventory or press retry. Selection must clear. Replugging
   must not silently substitute a target. No interface-open step exists here.

Automated regressions simulate removal/replug, multiple probes, missing
dependencies, failures, repeated clicks and late completion during close.
Actual host inventory and Windows Qt layout observations, commands, source
hashes and remaining validation limits are recorded with this increment's
[evidence record](../../../apps/GSHC/docs/evidence/host_probe_20261013/README.md).
Simulated cases are not physical hotplug or target verification.

## Connection diagnosis and localized states (15:23 UTC follow-up)

The maintenance serial status now distinguishes **未连接**, **串口已打开；等待固件**,
**串口已打开；固件有响应**, and **串口已打开；状态不可用**. These are separate from
probe discovery and SWD selection. Unsupported LOGFILE or unavailable status
does not by itself close the serial port or prove a physical disconnect.

The actual host inventory at 2026-10-13 15:23 UTC found Horco CMSIS-DAP
`FAED:4870`, serial `132765403520`, and matching USB serial **COM9**. COM7/COM8
were Bluetooth serial devices. A fresh source GUI on this host selected COM8
initially while independently selecting the Horco probe; it did not create a
maintenance connection. This is a reproduced startup observation, not a read
of the user's already-running GUI or a hardcoded port assignment. Select the
intended maintenance port explicitly; a selected SWD probe never opens it.

This task did not open COM9 or send any firmware command. The existing Windows
serial backend configures DTR/RTS on open; reset-free wiring and driver behavior
are unproven. pySerial also documents possible driver activation or glitches
on [serial open](https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.Serial.open).
The user explicitly required stopping at enumeration in that situation.
Port occupancy, UART wiring, flashed firmware identity and actual firmware
response remain unknown. Prior FINAL source described USART3 PB10/PB11 at
230400 8N1; that is not verification of today's flashed device or connections.

See the [alignment and diagnosis evidence](../../../apps/GSHC/docs/evidence/host_probe_alignment_20261013/README.md).
