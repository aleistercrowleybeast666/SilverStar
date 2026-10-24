"""Byte progress independent of Qt, protocol framing and verification success."""
from dataclasses import dataclass, replace
import time


@dataclass(frozen=True)
class TransferProgress:
    received: int
    total: int | None
    stage: str
    index: int = 0
    count: int = 0
    detail: str = ''


class ProgressThrottle:
    """Bound queued GUI notifications; stage changes and final outcomes are immediate."""
    def __init__(self, emit, *, interval=.1, clock=time.monotonic):
        self.emit, self.interval, self.clock = emit, interval, clock
        self.last = None
        self.pending = None
        self.at = float('-inf')

    def __call__(self, value):
        self.pending = value
        now = self.clock()
        changed = self.last is None or (value.stage,value.index) != (self.last.stage,self.last.index)
        if changed or value.stage in {'complete','failed','cancelled'} or now-self.at >= self.interval:
            self.emit(value)
            self.at = now
            self.last = value

    def flush(self, stage):
        if self.pending is not None:
            self(replace(self.pending,stage=stage))


class BatchProgress:
    def __init__(self, identifiers, sizes, emit):
        self.ids = tuple(identifiers)
        self.sizes = {identifier:sizes.get(identifier) for identifier in self.ids}
        self.emit = emit
        self.completed = 0
        self.received = 0
        self.index = 0

    def update(self, identifier, done, total, stage):
        if total is not None:
            self.sizes[identifier] = total
        self.index = self.ids.index(identifier)+1
        self.received = self.completed+done
        self.send(stage, f'Mission {identifier:06d}')

    def send(self, stage, detail=''):
        sizes = tuple(self.sizes.values())
        total = sum(sizes) if all(type(size) is int and size>=0 for size in sizes) else None
        self.emit(TransferProgress(self.received,total,stage,self.index,len(self.ids),detail))


__all__ = ['TransferProgress','ProgressThrottle','BatchProgress']
