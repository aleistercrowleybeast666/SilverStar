"""Finite reference models, never registered as host or target production owners.

These models make proposed invariants executable. Sequential interleavings do
not prove actual RTOS critical sections, hardware timing or transport shutdown.
"""
from dataclasses import dataclass
from enum import Enum


class ModelResult(str, Enum):
    Ok = "OK"
    Selected = "SELECTED"
    Skipped = "FIXED_STRIDE_SKIP"
    Busy = "BUSY"
    Failed = "FAILED"
    Unproven = "NOT_PROVEN"


class NativeSelector:
    """Observe every native frame; selection never examines sample values."""
    def __init__(self, stride, phase, native_timeout_us, selected_max_us, start_us=0):
        if (type(stride) is not int or not 1 <= stride <= 65535 or type(phase) is not int
                or not 0 <= phase < stride or any(type(v) is not int or v <= 0
                    for v in (native_timeout_us, selected_max_us)) or type(start_us) is not int
                or not 0 <= start_us < 2**64):
            raise ValueError("bounded selector parameters")
        self.stride, self.phase = stride, phase
        self.native_timeout, self.selected_max = native_timeout_us, selected_max_us
        self.modulo = 0
        self.previous = None
        self.native_last = self.selected_last = self.now = start_us
        self.failed = False

    def Poll(self, now_us):
        if type(now_us) is not int or not 0 <= now_us < 2**64:
            raise ValueError("owner timestamp")
        if (self.failed or (self.now is not None and now_us < self.now)
                or (self.native_last is not None and now_us-self.native_last >= self.native_timeout)
                or (self.selected_last is not None and now_us-self.selected_last > self.selected_max)):
            self.failed = True
            return ModelResult.Failed
        self.now = now_us
        return ModelResult.Ok

    def Feed(self, sequence, sample_us, receive_us, values):
        # values is retained by the caller. Deliberately never read here.
        if (type(sequence) is not int or not 0 <= sequence < 2**32
                or type(sample_us) is not int or not 0 <= sample_us <= receive_us):
            raise ValueError("native source fields")
        if self.Poll(receive_us) == ModelResult.Failed:
            return ModelResult.Failed
        if self.previous is not None and ((sequence-self.previous[0]) % 2**32 != 1 or sample_us <= self.previous[1]):
            self.failed = True
            return ModelResult.Failed
        self.previous, self.native_last = (sequence, sample_us), receive_us
        selected = self.modulo == self.phase
        self.modulo = (self.modulo+1) % self.stride
        if selected:
            self.selected_last = receive_us
            return ModelResult.Selected
        return ModelResult.Skipped


@dataclass(frozen=True)
class LeaseToken:
    generation: int
    owner: str


class SessionLeaseModel:
    """One logical gate for every entrant; local/remote cleanup stay distinct."""
    def __init__(self, entrants):
        self.entrants = tuple(entrants)
        self.token = None
        self.generation = 0
        self.state = "FREE"
        self.producer_stopped = self.reader_stopped = False
        self.consumer_active = False

    def Acquire(self, owner):
        if owner not in self.entrants: raise ValueError("unknown entrant")
        if self.token is not None or self.state != "FREE" or self.generation >= 2**32-1:
            return ModelResult.Busy, None
        self.generation += 1
        self.token = LeaseToken(self.generation, owner)
        self.state = "ACTIVE"
        self.producer_stopped = self.reader_stopped = self.consumer_active = False
        return ModelResult.Ok, self.token

    def CanPublish(self, token):
        return token == self.token and self.token is not None and self.state == "ACTIVE"

    def ConsumerAcquire(self, token):
        if not self.CanPublish(token) or self.consumer_active: return ModelResult.Busy
        self.consumer_active = True
        return ModelResult.Ok

    def Cancel(self, token):
        if token != self.token or token is None: return ModelResult.Failed
        self.state = "CANCELLING"
        return ModelResult.Ok

    def Acknowledge(self, token, *, producer=False, consumer=False, reader=False):
        if token != self.token or self.state != "CANCELLING": return ModelResult.Failed
        if producer: self.producer_stopped = True
        if consumer: self.consumer_active = False
        if reader: self.reader_stopped = True
        return ModelResult.Ok

    def Release(self, token, *, remote_confirmed, local_release_confirmed):
        if token != self.token or token is None: return ModelResult.Failed
        if (self.state != "CANCELLING" or not self.producer_stopped or not self.reader_stopped
                or self.consumer_active or not remote_confirmed or not local_release_confirmed):
            return ModelResult.Unproven
        self.token = None
        self.state = "FREE"
        return ModelResult.Ok

    def RevokeForRecovery(self):
        if self.token is not None: self.state = "CANCELLING"


@dataclass(frozen=True)
class CancelBound:
    result: ModelResult
    known_wire_us: int
    total_us: int | None
    unknown_terms: tuple


def CancelBound_Evaluate(baud, normal_bytes, priority_bytes, ack_bytes, terms, goal_us=500000):
    """Integer ceil of 8N1 wire time. Unknown execution terms remain unknown."""
    for value in (baud, normal_bytes, priority_bytes, ack_bytes, goal_us):
        if type(value) is not int or value < 0: raise ValueError("finite nonnegative budget")
    if baud == 0 or goal_us == 0: raise ValueError("nonzero rate/deadline")
    required = ("host_interrupt", "rx_parse", "schedule_isr", "producer_stop", "consumer_ack",
                "other_writers", "hal_dma_fault", "host_reader")
    if type(terms) is not dict or set(terms) != set(required): raise ValueError("complete path terms")
    for value in terms.values():
        if value is not None and (type(value) is not int or value < 0): raise ValueError("execution bound")
    unknown = tuple(name for name in required if terms[name] is None)
    wire = ((normal_bytes+priority_bytes+ack_bytes)*10*1000000 + baud-1)//baud
    if unknown: return CancelBound(ModelResult.Unproven, wire, None, unknown)
    total = wire+sum(terms.values())
    return CancelBound(ModelResult.Ok if total <= goal_us else ModelResult.Failed, wire, total, ())
