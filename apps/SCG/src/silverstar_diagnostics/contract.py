"""Bounded pure-data descriptions. Canonical contracts live in contracts/."""
from enum import Enum
import hashlib
import json
from pathlib import Path
import re


class DiagnosticResult(Enum):
    Ok = 'ok'
    InvalidFile = 'invalid_file'
    Unsupported = 'unsupported'
    Cancelled = 'cancelled'
    Timeout = 'timeout'
    Mismatch = 'mismatch'


class DiagnosticError(ValueError):
    def __init__(self, result, detail):
        super().__init__(detail)
        self.result = result


def Require(condition, detail, result=DiagnosticResult.InvalidFile):
    if not condition:
        raise DiagnosticError(result, detail)


def Bytes_Read(path, limit):
    path = Path(path)
    Require(path.is_file(), 'Input is not a regular file')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    Require(len(data) <= limit, 'Input exceeds size limit')
    return data


def _Pairs(pairs):
    result = {}
    for key, value in pairs:
        Require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def Json_Read(path, limit=65536):
    raw = Bytes_Read(path, limit)
    # Check depth lexically before json.loads can recurse. Strings do not count.
    depth = 0
    quoted = escaped = False
    for char in raw:
        if quoted:
            if escaped: escaped = False
            elif char == 92: escaped = True
            elif char == 34: quoted = False
        elif char == 34: quoted = True
        elif char in (91, 123):
            depth += 1
            Require(depth <= 12, 'JSON nesting exceeds 12')
        elif char in (93, 125): depth -= 1
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_Pairs,
                          parse_constant=lambda _: Require(False, 'Nonfinite JSON value'))
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise DiagnosticError(DiagnosticResult.InvalidFile, 'Malformed JSON') from exc


def Contract_Get():
    local = Path(__file__).with_name('swd_diagnostics_v1.json')
    path = local if local.is_file() else Path(__file__).parents[4] / 'contracts/swd_diagnostics_v1.json'
    return Json_Read(path)


def Schema_Create(target):
    Require(isinstance(target, str) and re.fullmatch(r'[A-Za-z0-9_+-]{1,64}', target), 'Invalid target name')
    return dict(format='SilverStar.ssdiag', version=1, target=target,
                diagnostics='silverstar.swd-diagnostics/1',
                entries=[item['id'] for item in Contract_Get()['entries']], binding=None)


def Schema_Validate(value):
    Require(type(value) is dict and set(value) == {'format','version','target','diagnostics','entries','binding'},
            'Unknown or missing descriptor fields')
    Require(value['format'] == 'SilverStar.ssdiag' and type(value['version']) is int and value['version'] == 1,
            'Unsupported descriptor format/version', DiagnosticResult.Unsupported)
    expected = Schema_Create(value['target'])
    Require(value['diagnostics'] == expected['diagnostics'], 'Unsupported diagnostic contract', DiagnosticResult.Unsupported)
    entries = value['entries']
    Require(type(entries) is list and 1 <= len(entries) <= 16 and all(type(x) is str for x in entries), 'Invalid entries')
    Require(len(entries) == len(set(entries)) and set(entries) <= set(expected['entries']), 'Unknown/duplicate diagnostic IDs')
    binding = value['binding']
    if binding is not None:
        Require(type(binding) is dict and set(binding) == {'elf','sha256','segments','fields'}, 'Invalid binding fields')
        Require(type(binding['elf']) is str and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}\.elf', binding['elf']) and
                '..' not in binding['elf'] and ':' not in binding['elf'], 'ELF must be a safe sibling basename')
        Require(type(binding['sha256']) is str and re.fullmatch('[0-9a-f]{64}', binding['sha256']), 'Invalid ELF hash')
        Require(type(binding['segments']) is list and 1 <= len(binding['segments']) <= 32, 'Invalid segment manifest')
        Require(type(binding['fields']) is list and len(binding['fields']) <= 16, 'Invalid resolved fields')
    return value


def Sha256(data):
    return hashlib.sha256(data).hexdigest()
