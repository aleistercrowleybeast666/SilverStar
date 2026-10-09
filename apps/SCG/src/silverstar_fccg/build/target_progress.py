"""Measured make targets; recipe launch is never credited as completion."""
from collections import Counter
from dataclasses import dataclass
import re

from silverstar_fccg.build.runner import BuildPlan, BuildProgress

_MARKER = re.compile(r'^FCCG_PROGRESS\|(COMPILE|LINK|HEX|BIN|SIZE)_(BEGIN|DONE)\|(.+)$')
_DRY_MARKER = re.compile(r'FCCG_PROGRESS\|(COMPILE|LINK|HEX|BIN|SIZE)_DONE\|([^"\r\n]+)')
_OUTPUT = re.compile(r'(?:^|\s)-o\s*(?:"([^"]+)"|\x27([^\x27]+)\x27|(\S+))')
_CHILD = re.compile(r'^(?:Putting|Live) child ([0-9A-Fa-fx]+) \((.+)\) PID\b')
_REAP = re.compile(r'^Reaping (winning|losing) child ([0-9A-Fa-fx]+) PID\b')
_REMOVE = re.compile(r'^Removing child ([0-9A-Fa-fx]+) PID\b')
_DEBUG_PREFIXES = ('Using jobserver', 'Need a job token', 'Obtained token', 'Released token',
    'Putting child ', 'Live child ', 'Reaping ', 'Removing child ', 'CreateProcess(',
    'Creating temporary batch file ', 'Cleaning up temp batch file ', 'Batch file contents:')


def _Path_Normalize(value):
    return value.strip().strip('"\x27').replace('\\', '/').removeprefix('./')


def _CommandUnit_Get(line):
    output = _OUTPUT.search(line)
    if output:
        target = _Path_Normalize(next(value for value in output.groups() if value is not None))
        if target.endswith('.o') and re.search(r'(?:^|\s)-c(?:\s|$)', line):
            return 'COMPILE', target
        if target.endswith('.elf'):
            return 'LINK', target
    copy = re.search(r'\b\S*objcopy(?:\.exe)?\s+.*(?:\s)("[^"]+"|\S+)\s*$', line)
    if copy:
        target = _Path_Normalize(copy.group(1))
        if target.endswith(('.bin', '.hex')):
            return ('BIN' if target.endswith('.bin') else 'HEX'), target
    size = re.search(r'>\s*("[^"]+\.size"|\S+\.size)\s*$', line)
    if size:
        return 'SIZE', _Path_Normalize(size.group(1))
    return None


@dataclass(frozen=True)
class TargetProgressPlan:
    units: tuple[tuple[str, str], ...]
    markers: bool
    no_work: bool = False

    @property
    def build_plan(self):
        counts = Counter(stage for stage, _subject in self.units)
        return BuildPlan(len(self.units), counts['COMPILE'], tuple(counts.items()))

    @classmethod
    def FromLines_Get(cls, lines):
        markers = tuple((match.group(1), _Path_Normalize(match.group(2)))
                        for line in lines for match in _DRY_MARKER.finditer(line))
        units = markers or tuple(unit for line in lines if (unit := _CommandUnit_Get(line)))
        visible = [line.strip() for line in lines if line.strip()]
        no_work = not units and (not visible or all('Nothing to be done' in line or 'is up to date' in line for line in visible))
        return cls(tuple(dict.fromkeys(units)), bool(markers), no_work)


class TargetProgressTracker:
    def __init__(self, plan, progress_callback, line_callback):
        self.plan = plan
        self.progress_callback = progress_callback
        self.line_callback = line_callback
        self.completed = set()
        self.children = {}
        self.reaped = {}
        self.output_lines = 0
        self.by_target = {subject: (stage, subject) for stage, subject in plan.units}
        self.stage_totals = Counter(stage for stage, _ in plan.units)

    def Progress_Report(self, stage, subject='', done=False):
        unit = (stage, subject)
        if done:
            if unit not in self.plan.units or unit in self.completed:
                return
            self.completed.add(unit)
        if self.progress_callback:
            stage_completed = sum(item[0] == stage for item in self.completed)
            self.progress_callback(BuildProgress(stage, len(self.completed), len(self.plan.units),
                subject, stage_completed, self.stage_totals.get('COMPILE' if stage == 'PLAN' else stage, 0)))

    def Line_Report(self, line):
        value = line.strip('\r\n')
        if self.plan.markers:
            marker = _MARKER.fullmatch(value.strip().strip('"'))
            if marker:
                self.Progress_Report(marker.group(1), _Path_Normalize(marker.group(3)), marker.group(2) == 'DONE')
                return
        else:
            child = _CHILD.match(value)
            if child:
                pointer, target = child.groups()
                target = _Path_Normalize(target)
                if value.startswith('Putting'):
                    self.reaped.pop(pointer, None)
                    if target in self.by_target:
                        self.Progress_Report(*self.by_target[target])
                self.children[pointer] = target
                return
            reap = _REAP.match(value)
            if reap:
                self.reaped[reap.group(2)] = reap.group(1) == 'winning'
                return
            removed = _REMOVE.match(value)
            if removed:
                pointer = removed.group(1)
                target = self.children.pop(pointer, None)
                winning = self.reaped.pop(pointer, False)
                if winning and target in self.by_target:
                    self.Progress_Report(*self.by_target[target], done=True)
                return
            if value.startswith(_DEBUG_PREFIXES) or value.startswith('\t'):
                return
        self.output_lines += 1
        if not self.plan.units and not self.plan.no_work and self.progress_callback:
            self.progress_callback(BuildProgress('UNMEASURED', 0, 0, 'build_output', self.output_lines, 0))
        if self.line_callback:
            self.line_callback(value)
