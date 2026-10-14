"""Experimental pinned ST-Link transport; no board/core or target initialization.

Uses installed Apache-2.0 pyOCD. USB lifecycle/padding adaptation follows its
STLinkUSBInterface (Arm Limited/Chris Reed); dependency licenses remain upstream.
Only a claimed interface can send the narrowly checked transport/read commands.
"""
import os
import struct
import time
from transport.swd_session import SwdError, SwdResult as R
from transport.swd_backends import ProbeKind_Get, SwdBackendKind, STLINK_PIDS
from transport._swd_pyocd import PyOcdMemAp, _LoadLibrary, _LibraryOwner


def _LoadStlinkLibrary():
    api = _LoadLibrary()
    from pyocd.probe.stlink import usb
    from pyocd.probe.stlink_probe import StlinkProbe
    api.stusb, api.StlinkProbe = usb, StlinkProbe
    return api


def _Interface(api, device, owner):
    usb = api.stusb.usb

    class ScopedStlink(api.stusb.STLinkUSBInterface):
        def __init__(self):
            self._claimed = False
            self.enter_sent = False
            self.idle_confirmed = False
            self.read_window = None
            super().__init__(device)
            self._expected_pid = device.idProduct
            self._expected_serial = self.serial_number

        def open(self):
            owner._guard()
            raw_serial = self._dev.serial_number
            serial = raw_serial.encode('utf-16-le')[::2].hex().upper() if len(raw_serial)==12 else raw_serial
            if (self._dev.idVendor != 0x0483 or self._dev.idProduct != self._expected_pid or
                    serial.upper() != self._expected_serial.upper()):
                raise SwdError(R.TargetMismatch, 'ST-Link USB identity changed')
            config = self._dev.get_active_configuration()
            interface = config[(0,0)]
            endpoints = tuple(interface)
            self._ep_out = next((e for e in endpoints if e.bEndpointAddress==self._info.out_ep),None)
            self._ep_in = next((e for e in endpoints if e.bEndpointAddress==self._info.in_ep),None)
            if self._ep_out is None or self._ep_in is None:
                raise SwdError(R.Unsupported, 'ST-Link interface0 bulk endpoints unavailable')
            self._max_packet_size = self._ep_in.wMaxPacketSize
            if not 1 <= self._max_packet_size <= 1024:
                raise SwdError(R.Unsupported, 'ST-Link packet size outside approved bound')
            try:
                result = usb.util.claim_interface(self._dev,0)
            except usb.core.USBError as exc:
                raise SwdError(R.Busy, f'ST-Link claim refused; no protocol command sent: {exc}') from exc
            self._claimed = True
            if result is not None:
                raise SwdError(R.TransportError, 'Unexpected interface claim result')
            self._closed = False
            self._flush_rx()

        def _flush_rx(self):
            for _ in range(64):
                owner._guard()
                try: self._ep_in.read(self._max_packet_size,1)
                except usb.core.USBTimeoutError: return
            raise SwdError(R.TransportError, 'ST-Link receive drain exceeds64 packets')

        def _allowed(self, cmd, read_size):
            if cmd in (b'\xF1',b'\xFB',b'\xF5',b'\xF7'):
                return read_size == {0xF1:6,0xFB:12,0xF5:2,0xF7:8}[cmd[0]]
            if cmd == b'\xF2\x30\xA3\x00':
                return read_size==2 and self.idle_confirmed and not self.enter_sent
            if cmd == b'\xF2\x21': return read_size is None and self.enter_sent
            if cmd == b'\xF2\x4B\x00\x00': return read_size==2 and self.enter_sent
            if cmd == b'\xF2\x43\x03': return read_size==2 and not self.enter_sent
            if cmd == b'\xF2\x63\x01': return read_size==8 and not self.enter_sent
            if cmd == b'\xF2\x62\x00': return read_size==52 and not self.enter_sent
            if len(cmd)==8 and cmd[:4]==b'\xF2\x61\x00\x00':
                return read_size==8 and 1 <= int.from_bytes(cmd[4:],'little') <= 1000 and not self.enter_sent
            if len(cmd)==6 and cmd[:2]==b'\xF2\x45':
                return read_size==8 and self.enter_sent and struct.unpack('<HH',cmd[2:]) in ((0xFFFF,0),(0,0xFC))
            if cmd == b'\xF2\x3E': return read_size==12 and self.enter_sent and self.read_window is not None
            # Only the installed driver's SWD sticky-fault clearing, no DAPABORT/reset.
            if cmd == b'\xF2\x46\xFF\xFF\x00\x00\x1E\x00\x00\x00':
                return read_size==2 and self.enter_sent and self.read_window is not None
            if len(cmd)==12 and cmd[:2] in (b'\xF2\x07',b'\xF2\x0C'):
                addr,n = struct.unpack('<IH',cmd[2:8])
                window = self.read_window
                aligned = cmd[1]!=7 or addr%4==0 and n%4==0
                return (self.enter_sent and window is not None and 1 <= n <= 1024 and read_size==n and
                        cmd[8:]==b'\x00'*4 and aligned and owner._ReadAllowed(addr,n) and
                        window[0] <= addr < addr+n <= window[0]+window[1])
            return False

        def transfer(self, cmd, writeData=None, readSize=None, timeout=1000):
            owner._guard()
            try: raw = bytes(cmd)
            except (ValueError,TypeError) as exc: raise SwdError(R.InvalidRequest,'Invalid ST-Link command bytes') from exc
            if (not self._claimed or writeData is not None or not 1 <= len(raw) <= 16 or
                    (readSize is not None and (type(readSize) is not int or not 1 <= readSize <= 1024)) or
                    not self._allowed(raw,readSize)):
                raise SwdError(R.SafetyNotProven,'ST-Link command/operand outside the read-only profile')
            if raw==b'\xF2\x30\xA3\x00': self.enter_sent=True
            try:
                count=self._ep_out.write(raw+b'\x00'*(16-len(raw)),500)
                if count!=16: raise SwdError(R.TransportError,'Incomplete ST-Link command write')
                data=None
                if readSize is not None:
                    data=bytearray(self._ep_in.read(max(readSize,self._max_packet_size),500))
                    if len(data)<readSize: raise SwdError(R.TransportError,'Incomplete ST-Link command response')
                    data=data[:readSize]
            except usb.core.USBTimeoutError as exc:
                raise SwdError(R.Timeout,'ST-Link USB operation timed out') from exc
            except usb.core.USBError as exc:
                raise SwdError(R.TransportError,'ST-Link USB operation failed') from exc
            owner._guard()
            if raw==b'\xF5':
                if not self.enter_sent and data[0]!=1:
                    result=R.Busy if data[0]==2 else R.SafetyNotProven
                    raise SwdError(result,'ST-Link existing debug/DFU/SWIM/unknown mode is not changed')
                self.idle_confirmed=data[0]==1
            if raw==b'\xF2\x21': self.enter_sent=False
            return data

        def close(self):
            if self._claimed:
                result=usb.util.release_interface(self._dev,0)
                if result is not None: raise SwdError(R.ReleaseFailed,'Unexpected ST-Link release result')
                self._claimed=False
            if self._dev is not None:
                usb.util.dispose_resources(self._dev)
                self._dev=None
            self._closed=True
            self._ep_in=self._ep_out=self._ep_swv=None

    return ScopedStlink()


def _SelectInterface(api, selected, owner):
    matches=[]
    try:
        devices=api.stusb.usb_find(find_all=True,idVendor=0x0483,idProduct=int(selected.usb_id.split(':')[1],16))
        for index,device in enumerate(devices):
            owner._guard()
            if index>=32: raise SwdError(R.Busy,'ST-Link enumeration exceeds32 devices')
            if (device.idVendor,device.idProduct)!=(0x0483,int(selected.usb_id.split(':')[1],16)):
                api.stusb.usb.util.dispose_resources(device)
                raise SwdError(R.TargetMismatch,'ST-Link enumeration returned a different VID/PID')
            device.default_timeout=500
            try: interface=_Interface(api,device,owner)
            except Exception:
                api.stusb.usb.util.dispose_resources(device)
                raise
            if interface.serial_number.upper()==selected.serial.upper(): matches.append(interface)
            else: interface.close()
        if len(matches)!=1:
            raise SwdError(R.InvalidRequest,'Exact normalized ST-Link serial absent or ambiguous; no alternative selected')
        return matches.pop()
    except api.stusb.usb.core.NoBackendError as exc:
        raise SwdError(R.MissingDependency,'Existing compatible libusb backend/driver required; no installation attempted') from exc
    finally:
        for interface in matches: interface.close()


class StlinkMemAp(PyOcdMemAp):
    """Same trusted read ranges/budgets as CMSIS-DAP, with separate USB lifecycle."""
    def open(self, selected):
        if ProbeKind_Get(selected)!=SwdBackendKind.Stlink:
            raise SwdError(R.Unsupported,'ST-Link backend requires an admitted ST-Link USB profile')
        if not _LibraryOwner.acquire(blocking=False):
            raise SwdError(R.Busy,'Another SilverStar pyOCD operation owns the library session')
        self._owned=True
        self._deadline=time.monotonic()+self.TIMEOUT
        api=_LoadStlinkLibrary()
        self._interface=_SelectInterface(api,selected,self)
        self._probe=api.StlinkProbe(self._interface)
        self._link=self._probe._link
        self._session=api.Session(None,auto_open=False,options={'no_config':True,'project_dir':os.getcwd(),
            'logging':None,'connect_mode':'attach','resume_on_disconnect':False,'stlink.v3_prescaler':1})
        self._probe.session=self._session
        self._probe.open()
        if self._link._hw_version not in (2,3,4) or (self._link._hw_version==2 and self._link._jtag_version<28):
            raise SwdError(R.Unsupported,'ST-Link V2J28+ or reviewed V3/V4 firmware required for NO_CORE AP0')
        self._probe.set_clock(1000000)
        self._connect_attempted=True
        self._probe.connect(api.Protocol.SWD)
        memory=self._probe.get_memory_interface_for_ap(api.APv1Address(0))  # AP0 NO_CORE only.
        dp=self._link.read_dap_register(0xFFFF,0)
        ap=self._link.read_dap_register(0,0xFC)
        if (dp>>12)&15 not in (1,2) or (ap>>13)&15!=8 or ap&15!=1:
            raise SwdError(R.Unsupported,'Only ADIv5 DP1/2 with AP0 AHB MEM-AP is admitted')
        self._ap=memory
        if self._ap is None: raise SwdError(R.Unsupported,'ST-Link has no AP0 memory interface')
        self._guard()

    def read(self, address, length):
        if self._interface is None: raise SwdError(R.NotAttached,'ST-Link is not attached')
        if not self._ReadAllowed(address,length):
            raise SwdError(R.InvalidRequest,'Read outside trusted ST-Link ranges/bounds')
        self._interface.read_window=(address,length)
        try: return super().read(address,length)
        finally: self._interface.read_window=None

    def close(self):
        self._closing=True
        self._deadline=time.monotonic()+2
        disconnect_error=None
        if self._connect_attempted and self._probe is not None:
            try: self._probe.disconnect()
            except Exception as exc: disconnect_error=exc
            self._connect_attempted=False
        try:
            if self._interface is not None:
                self._interface.close()
                self._interface=None
        except Exception as exc:
            raise SwdError(R.ReleaseFailed,f'ST-Link interface release failed: {exc}') from exc
        self._ap=self._probe=self._link=self._session=None
        if disconnect_error is not None:
            raise SwdError(R.ReleaseFailed,f'ST-Link transport exit failed; host interface released: {disconnect_error}')
        if self._owned:
            _LibraryOwner.release()
            self._owned=False
