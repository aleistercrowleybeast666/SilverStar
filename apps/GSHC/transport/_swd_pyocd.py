"""Pinned pyOCD CMSIS-DAPv2/ADIv5 adapter; never constructs a board or core.

Only the selected Horco bulk interface is claimed. DP/AP configuration is
required for reads; no target address write, reset pin or CPU control is used.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from threading import Lock, Thread
import time
from types import SimpleNamespace

from transport.swd_session import SwdError, SwdResult, _ValidateProbe


_LibraryOwner = Lock()  # pyOCD Session.get_current() is process-global.
_VERSION = '0.45.1'
_DEFAULT_DEPS = Path(__file__).absolute().parents[3] / '.work/dev013_swd_pyocd01/deps'


def _LoadLibrary():
    directory = Path(os.environ.get('SILVERSTAR_SWD_PYOCD_PATH', str(_DEFAULT_DEPS))).absolute()
    if not (directory / 'pyocd/__init__.py').is_file():
        raise SwdError(SwdResult.MissingDependency,
            'Install pyOCD 0.45.1 in an isolated directory; set SILVERSTAR_SWD_PYOCD_PATH to that directory')
    loaded = sys.modules.get('pyocd')
    if loaded is not None and Path(loaded.__file__).absolute().parent != directory / 'pyocd':
        raise SwdError(SwdResult.SafetyNotProven, 'Another pyOCD installation is already loaded')
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    try:
        import pyocd
        if pyocd.__version__ != _VERSION:
            raise SwdError(SwdResult.SafetyNotProven, 'This adapter requires audited pyOCD 0.45.1')
        from pyocd.core.session import Session
        from pyocd.coresight.dap import DebugPort
        from pyocd.coresight.ap import AccessPort, MEM_AP, APv1Address
        from pyocd.probe.cmsis_dap_probe import CMSISDAPProbe
        from pyocd.probe.debug_probe import DebugProbe
        from pyocd.probe.pydapaccess.dap_access_cmsis_dap import DAPAccessCMSISDAP
        from pyocd.probe.pydapaccess.interface import pyusb_v2_backend as bulk
        return SimpleNamespace(Session=Session, DebugPort=DebugPort, AccessPort=AccessPort,
            MEM_AP=MEM_AP, APv1Address=APv1Address, Probe=CMSISDAPProbe,
            Protocol=DebugProbe.Protocol, Link=DAPAccessCMSISDAP, bulk=bulk)
    except ImportError as exc:
        raise SwdError(SwdResult.MissingDependency, f'Incomplete isolated pyOCD dependencies: {exc}') from exc


def _SelectDevice(api, serial, guard):
    matches = []
    try:
        for index, device in enumerate(api.bulk.usb_find(find_all=True, idVendor=0xFAED, idProduct=0x4870)):
            device.default_timeout = 500
            try:
                guard()
                if index >= 32:
                    raise SwdError(SwdResult.Busy, 'Horco USB enumeration exceeds 32 devices')
                if device.serial_number == serial:
                    matches.append(device)
                else:
                    api.bulk.usb.util.dispose_resources(device)
            except Exception:
                api.bulk.usb.util.dispose_resources(device)
                raise
        if len(matches) != 1:
            raise SwdError(SwdResult.InvalidRequest, 'Exact Horco USB serial is absent or ambiguous; no alternative selected')
        return matches.pop()
    finally:
        for device in matches:
            api.bulk.usb.util.dispose_resources(device)


def _BulkInterface(api, device, guard):
    """Small timeout/identity/cleanup adaptation of the upstream USB interface.

    Upstream open searches again by serial alone, start_rx drains without a bound,
    and close joins without a bound. Keep its packet I/O and receive task; narrow
    those three lifecycle boundaries without changing the installed dependency.
    """
    usb = api.bulk.usb

    class ScopedBulk(api.bulk.PyUSBv2):
        DEFAULT_USB_TIMEOUT_MS = 500
        DEFAULT_USB_TIMEOUT_S = .5

        def __init__(self):
            super().__init__(device)
            self.dev = device  # Also retained when configuration/claim fails.
            self._claimed = False

        def open(self):
            guard()
            if (self.dev.idVendor, self.dev.idProduct, self.dev.serial_number) != (0xFAED, 0x4870, self.serial_number):
                raise SwdError(SwdResult.TargetMismatch, 'USB identity changed before claim')
            config = self.dev.get_active_configuration()
            interface = usb.util.find_descriptor(config, custom_match=lambda item:
                item.bInterfaceNumber == 0 and api.bulk._match_cmsis_dap_v2_interface(item))
            if interface is None:
                raise SwdError(SwdResult.Unsupported, 'Selected probe requires CMSIS-DAPv2 bulk on MI00; HID fallback is disabled')
            endpoints = interface.endpoints()
            if len(endpoints) < 2:
                raise SwdError(SwdResult.Unsupported, 'CMSIS-DAPv2 endpoints are incomplete')
            self.intf_number = interface.bInterfaceNumber
            try:
                usb.util.claim_interface(self.dev, self.intf_number)
            except usb.core.USBError as exc:
                raise SwdError(SwdResult.Busy, f'USB interface claim refused; no DAP command sent: {exc}') from exc
            self._claimed = True
            self.ep_out, self.ep_in = endpoints[:2]
            self.ep_swo = None  # SWO is outside this read-only profile.
            self.closed = False
            self.start_rx()

        def start_rx(self):
            for _ in range(64):
                guard()
                try:
                    self.ep_in.read(self.ep_in.wMaxPacketSize, 1)
                except usb.core.USBTimeoutError:
                    break
            else:
                raise SwdError(SwdResult.TransportError, 'Probe receive drain exceeds 64 packets')
            self.thread = Thread(target=self.rx_task, name='SilverStar CMSIS-DAPv2 receive', daemon=True)
            self.thread.start()

        def write(self, data):
            guard()
            try:
                return super().write(data)
            except usb.core.USBTimeoutError as exc:
                raise SwdError(SwdResult.Timeout, 'CMSIS-DAP USB write timed out') from exc

        def read(self):
            guard()
            try:
                return super().read()
            except api.bulk.DAPAccessIntf.DeviceError as exc:
                if (str(exc).startswith('Timeout reading from probe ') or
                        isinstance(exc.__cause__, usb.core.USBTimeoutError)):
                    raise SwdError(SwdResult.Timeout, 'CMSIS-DAP USB read timed out') from exc
                raise

        def close(self):
            self.closed = True
            self.rx_stop_event.set()
            self.read_sem.release()
            if self.thread is not None:
                self.thread.join(2)
                if self.thread.is_alive():
                    raise SwdError(SwdResult.ReleaseFailed, 'USB receive thread did not exit; ownership retained')
                self.thread = None
            if self._claimed:
                usb.util.release_interface(self.dev, self.intf_number)
                self._claimed = False
            if self.dev is not None:
                usb.util.dispose_resources(self.dev)
                self.dev = None
            self.ep_out = self.ep_in = None

    return ScopedBulk()


def _DebugPort(api, probe, session):
    class ReadOnlyDP(api.DebugPort):
        # Session has no board/target, so pack/user debug-sequence hooks never run.
        def connect_debug_port_hook(self):
            return False

        def enable_debug_port_hook(self):
            return False

        def connect(self, protocol):
            self._protocol = protocol
            self.probe.lock()
            try:
                self._get_probe_capabilities()
                self._connect()
                if self.dpidr.version != 1:
                    raise SwdError(SwdResult.Unsupported, 'Only the audited ADIv5 DPv1/AP0 profile is implemented')
                self.clear_sticky_err()
                if not self.power_up_debug():
                    raise SwdError(SwdResult.Timeout, 'DP debug/system power acknowledgement timed out')
                self._check_version()
            finally:
                self.probe.unlock()  # Upstream CallSequence skips this on failure.

    return ReadOnlyDP(probe, SimpleNamespace(session=session))


class PyOcdMemAp:
    TIMEOUT = 10

    def __init__(self, cancel):
        self.cancel = cancel
        self._owned = False
        self._interface = self._link = self._probe = self._session = self._ap = None
        self._connect_attempted = False
        self._closing = False
        self._deadline = 0

    def _guard(self):
        if not self._closing and self.cancel.is_set():
            raise SwdError(SwdResult.Cancelled, 'SWD operation cancelled')
        if time.monotonic() >= self._deadline:
            raise SwdError(SwdResult.Timeout, 'SWD operation deadline reached')

    def open(self, selected):
        _ValidateProbe(selected)
        if not _LibraryOwner.acquire(blocking=False):
            raise SwdError(SwdResult.Busy, 'Another SilverStar pyOCD operation owns the library session')
        self._owned = True
        self._deadline = time.monotonic() + self.TIMEOUT
        api = _LoadLibrary()
        self._guard()
        device = _SelectDevice(api, selected.serial, self._guard)
        try:
            self._interface = _BulkInterface(api, device, self._guard)
        except Exception:
            api.bulk.usb.util.dispose_resources(device)
            raise
        self._link = api.Link(selected.serial, interface=self._interface)
        self._probe = api.Probe(self._link)
        # An options-only Session skips user scripts and Board construction. Explicit
        # project_dir is the existing cwd: Session's chdir does not change it.
        self._session = api.Session(None, auto_open=False, options={'no_config': True,
            'project_dir': os.getcwd(), 'logging': None, 'connect_mode': 'attach',
            'resume_on_disconnect': False, 'cmsis_dap.deferred_transfers': False,
            'cmsis_dap.limit_packets': True})
        self._probe.session = self._session
        self._probe.open()
        self._probe.set_clock(1000000)
        self._connect_attempted = True
        dp = _DebugPort(api, self._probe, self._session)
        dp.connect(api.Protocol.SWD)
        self._ap = api.AccessPort.create(dp, api.APv1Address(0))
        if not isinstance(self._ap, api.MEM_AP):
            raise SwdError(SwdResult.Unsupported, 'AP0 is not a memory access port')
        self._guard()

    def read(self, address, length):
        if self._ap is None:
            raise SwdError(SwdResult.NotAttached, 'MEM-AP is not attached')
        if (type(address) is not int or type(length) is not int or not 1 <= length <= 1024 or
                not ((address in (0xE000ED00, 0xE0042000, 0xE000EDF0) and length == 4) or
                     0x20000000 <= address < address + length <= 0x20020000 or
                     0x10000000 <= address < address + length <= 0x10010000)):
            raise SwdError(SwdResult.InvalidRequest, 'Backend read is outside the approved identity/RAM profile')
        self._deadline = time.monotonic() + self.TIMEOUT
        self._guard()
        data = bytes(self._ap.read_memory_block8(address, length))
        self._guard()
        return data

    def close(self):
        self._closing = True
        self._deadline = time.monotonic() + 2
        disconnect_error = None
        try:
            if self._connect_attempted and self._link is not None and self._link._is_open:
                try:
                    self._link.disconnect()  # CMSIS-DAP disconnect; no core resume/reset.
                except Exception as exc:
                    disconnect_error = exc
                self._connect_attempted = False
            # Even partially failed link/probe.open may leave a claimed interface.
            # Bypass their early-return flags and close our retained resource directly.
            if self._interface is not None:
                self._interface.close()
                self._interface = None
            self._ap = self._probe = self._link = self._session = None
            if disconnect_error is not None:
                raise SwdError(SwdResult.ReleaseFailed, f'DAP disconnect acknowledgement failed: {disconnect_error}')
        except Exception as exc:
            if isinstance(exc, SwdError):
                raise
            raise SwdError(SwdResult.ReleaseFailed, str(exc)) from exc
        if self._owned:
            _LibraryOwner.release()
            self._owned = False
