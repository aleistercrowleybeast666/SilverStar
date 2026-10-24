"""Opt-in full-session adapter serviced by the existing MaintenanceOwner thread.

No port is opened here. Each request has its own bounded result slot; a late
completion cannot satisfy a replacement request. Release never claims remote
cleanup: InstallationBackend owns that distinct acknowledgement.
"""
from dataclasses import dataclass, field
from queue import Empty, Full, Queue
from threading import Event, Lock
import time


class _Cancellation:
    def __init__(self, *events): self.events = events
    def is_set(self): return any(event.is_set() for event in self.events)


@dataclass
class _Exchange:
    payload: bytes
    deadline: float
    cancel: Event
    result: Queue = field(default_factory=lambda: Queue(1))
    abandoned: Event = field(default_factory=Event)


class InstallationOwnerProvider:
    def __init__(self, owner, *, enabled=False):
        self.owner, self.enabled = owner, enabled is True

    def Acquire(self, name):
        if not self.enabled or name != "installation": return None
        return self.owner.AcquireInstallationSession()


class InstallationOwnerLease:
    """Queue-backed caller handle. Only Service runs in the port owner thread."""
    def __init__(self):
        self.requests = Queue(1)
        self.release_requested, self.detached, self.abort = Event(), Event(), Event()
        self._request_lock = Lock()
        self._closed = False
        self.service_error = None

    def Request(self, payload, *, deadline, cancel):
        if (type(payload) is not bytes or not payload.endswith(b"\r\n") or len(payload)>193
                or not isinstance(cancel, Event) or not 0<deadline-time.monotonic()<=120):
            raise ValueError("BOUNDED_INSTALLATION_EXCHANGE")
        if self._closed or self.release_requested.is_set() or self.detached.is_set():
            raise OSError("INSTALLATION_LEASE_CLOSED")
        if cancel.is_set(): raise InterruptedError("INSTALLATION_CANCELLED_BEFORE_QUEUE")
        if not self._request_lock.acquire(False): raise RuntimeError("ONE_INSTALLATION_EXCHANGE")
        request = _Exchange(payload, deadline, cancel)
        try:
            self.requests.put_nowait(request)
            while True:
                if cancel.is_set():
                    request.abandoned.set(); raise InterruptedError("INSTALLATION_CANCELLED_DURING_EXCHANGE")
                remaining = deadline-time.monotonic()
                if remaining<=0:
                    request.abandoned.set(); raise TimeoutError("INSTALLATION_REQUEST_DEADLINE")
                if self.detached.is_set(): raise OSError("INSTALLATION_OWNER_DETACHED")
                try: success, value = request.result.get(timeout=min(.02,remaining))
                except Empty: continue
                if time.monotonic()>=deadline:
                    request.abandoned.set(); raise TimeoutError("INSTALLATION_LATE_RESULT")
                if cancel.is_set(): raise InterruptedError("INSTALLATION_CANCELLED_AT_RESULT")
                if success: return value
                raise value
        except Full as exc:
            raise RuntimeError("INSTALLATION_REQUEST_SLOT_BUSY") from exc
        finally:
            self._request_lock.release()

    def Service(self, transport, stop):
        try:
            transport.prepare_job()
            while not stop.is_set() and not self.release_requested.is_set():
                try: request = self.requests.get(timeout=.02)
                except Empty: continue
                try:
                    if request.abandoned.is_set() or time.monotonic()>=request.deadline:
                        raise TimeoutError("INSTALLATION_EXPIRED_BEFORE_SEND")
                    cancel = _Cancellation(stop,self.abort,request.cancel,request.abandoned)
                    result = transport.installation_exchange(request.payload,request.deadline,cancel)
                    if cancel.is_set(): raise InterruptedError("INSTALLATION_EXCHANGE_ABANDONED")
                    if time.monotonic()>=request.deadline: raise TimeoutError("INSTALLATION_LATE_TRANSPORT_RESULT")
                    request.result.put_nowait((True,result))
                except Exception as exc:
                    from services.device_export import ExportCancelled
                    if isinstance(exc,ExportCancelled): exc=InterruptedError(str(exc))
                    request.result.put_nowait((False,exc))
                finally: self.requests.task_done()
        except Exception as exc:
            self.service_error = exc
        finally:
            self._closed = True
            for _ in range(1):
                try: request = self.requests.get_nowait()
                except Empty: break
                request.result.put_nowait((False,OSError("INSTALLATION_OWNER_STOPPED")))
                self.requests.task_done()

    def OwnerDetached(self):
        # Called after the owner's claim is released, never by Request callers.
        self._closed = True
        self.detached.set()

    def Release(self):
        self.release_requested.set()
        if not self.detached.wait(1.): return False
        return self.service_error is None


__all__ = ["InstallationOwnerProvider", "InstallationOwnerLease"]
