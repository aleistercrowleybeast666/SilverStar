"""Reviewed read-only, single-line console commands. No implicit control path.

Authority: maintenance protocol0.1 documentation and SystemConsole handlers.
The GUI may explicitly confirm an unlisted raw command. Dedicated control flows
still own mission/control operations; remote deletion stays disabled.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ConsoleCommand:
    text: str


COMMANDS = (
    ('SYSTEM INFO','版本与构建身份','Firmware/build identity'),
    ('SYSTEM STATUS','生命周期、准备与阻塞','Lifecycle/readiness/blocking'),
    ('SYSTEM READY','准备条件及未就绪字段','Readiness conditions'),
    ('SYSTEM CAPABILITIES','已编译/启用/存在/健康能力','Capabilities masks'),
    ('SYSTEM STARTUP','启动检查报告；可选IMU/GNSS/TELEMETRY','Startup report; optional IMU/GNSS/TELEMETRY'),
    ('SYSTEM STACK','任务栈观测，不是完整栈证明','Task stack observations, not a stack proof'),
    ('SYSTEM DIAG','分组诊断；可选游标0..16','Grouped diagnostics; optional cursor0..16'),
    ('SYSTEM START RESULT','最近console START请求结果，仅查询','Last console START result, query only'),
    ('CAL STATUS','校准阶段与就绪标志','Calibration state/readiness'),
    ('CAL DETAIL','校准采样及等待原因','Calibration samples/wait reasons'),
    ('ALIGN STATUS','对准状态','Alignment status'),('ALIGN DETAIL','对准详细观测','Alignment details'),
    ('ESTIMATOR STATUS','估计器状态','Estimator status'),('ESTIMATOR GNSS','GNSS融合观测','GNSS fusion observations'),
    ('ESTIMATOR BARO','气压融合观测','Barometer fusion observations'),('INS STATUS','惯导解算有效性','INS validity'),
    ('LOG STATUS','存储状态；写尝试不等于完成','Storage status; attempts are not completions'),
    ('LOGFILE CAPS','文件服务能力','File-service capabilities'),('LOGFILE STATUS','日志与维护快照，不进入维护','File/maintenance snapshot; no ENTER'),
    ('TIME STATUS','时基与UTC诊断','Time/UTC diagnostics'),
)
_EXACT = frozenset(row[0] for row in COMMANDS)
INDEXED_MODULES=('IMU','GNSS','BARO','MAG','ATTITUDE','TELEMETRY','POWER')


@dataclass(frozen=True)
class CommandDefinition:
    module: str
    verb: str
    indexed: bool = False
    parameters: str = ''
    default: str = ''
    required: bool = False
    file_v1: bool = False


def ConsoleCatalog_Get(file_v1=False):
    """SystemConsole indexed/system grammar; LOGFILE args follow FileServiceClient."""
    rows=[CommandDefinition(*row[0].split(' ',1),parameters=(
        '0..16 (optional)' if row[0]=='SYSTEM DIAG' else
        'IMU / GNSS / TELEMETRY (optional)' if row[0]=='SYSTEM STARTUP' else '')) for row in COMMANDS]
    for module in INDEXED_MODULES:
        rows.append(CommandDefinition(module,'LIST'))
        rows.extend(CommandDefinition(module,verb,True) for verb in
                    ('INFO','STATUS','CAPABILITIES','SAMPLE','IO','CONFIG SHOW','CONFIG READ','CONFIG VERIFY'))
    rows.extend((CommandDefinition('GNSS','SAMPLE DETAIL',True),
                 CommandDefinition('GNSS','NAV SAT',True),CommandDefinition('GNSS','MON RF',True),
                 CommandDefinition('BARO','SAMPLE DETAIL',True)))
    if file_v1:
        rows.extend((CommandDefinition('LOGFILE','ENTER',file_v1=True),
            CommandDefinition('LOGFILE','LIST',parameters='cursor',default='0',required=True,file_v1=True),
            CommandDefinition('LOGFILE','META',parameters='id',required=True,file_v1=True),
            CommandDefinition('LOGFILE','READ',parameters='id token offset',required=True,file_v1=True),
            CommandDefinition('LOGFILE','POLL',parameters='request_id',required=True,file_v1=True),
            CommandDefinition('LOGFILE','CANCEL',file_v1=True)))
    return tuple(rows)


def ConsoleCommand_IsKnown(text):
    command=' '.join(text.strip().upper().split())
    if command in _EXACT or re.fullmatch(r'SYSTEM DIAG (?:[0-9]|1[0-6])',command):return True
    if command in ('SYSTEM STARTUP IMU','SYSTEM STARTUP GNSS','SYSTEM STARTUP TELEMETRY'):return True
    parts=command.split()
    if len(parts)>=3 and parts[0] in INDEXED_MODULES and parts[1].isdigit() and int(parts[1])<=255:
        return any(row.module==parts[0] and row.indexed and row.verb==' '.join(parts[2:]) for row in ConsoleCatalog_Get())
    if len(parts)==2 and parts[0] in INDEXED_MODULES and parts[1]=='LIST':return True
    return bool(re.fullmatch(r'LOGFILE (?:ENTER|CANCEL|LIST [0-9]+|META [0-9]+|READ [0-9]+ 1-[0-9A-F]{8}-[0-9A-F]{8} [0-9]+|POLL [0-9]+)',command))


def ConsoleCommand_Validate(text, *, allow_raw=False):
    if type(text) is not str or not 1 <= len(text) <= 191 or not text.isascii() or any(ord(c)<32 or ord(c)==127 for c in text):
        raise ValueError('Invalid command; one bounded ASCII line required')
    command = ' '.join(text.strip().upper().split())
    if not command:raise ValueError('Empty maintenance command')
    if command in _EXACT:
        return command
    if re.fullmatch(r'SYSTEM DIAG (?:[0-9]|1[0-6])',command):
        return command
    if command in ('SYSTEM STARTUP IMU','SYSTEM STARTUP GNSS','SYSTEM STARTUP TELEMETRY'):
        return command
    if allow_raw:
        if (re.match(r'^SYSTEM START(?:\s|$)',command) and command!='SYSTEM START RESULT' or
                re.match(r'^(?:SYSTEM (?:RESET|REBOOT|UNLOCK|LOCK)\b|OUTPUT\b|(?:CAL|ALIGN) (?:START|STOP|RESET)\b|LOGFILE DELETE\b)',command)):
            raise ValueError('Use the dedicated control workflow; remote deletion is disabled')
        return ' '.join(text.strip().split())
    raise ValueError('Unknown, unsupported or side-effect command; use the dedicated confirmed workflow')


def ConsoleCommand_ResponsePrefix(command):
    command = ConsoleCommand_Validate(command,allow_raw=True)
    parts=command.split()
    if command in ('SYSTEM START RESULT','SYSTEM STARTUP IMU','SYSTEM STARTUP GNSS','SYSTEM STARTUP TELEMETRY'):
        return command
    if len(parts)>=3 and parts[0]=='MAG' and parts[1].isdigit() and parts[2] in ('STREAM','CAL'):
        return ' '.join(parts[:3])
    count=len(parts) if parts[0] in INDEXED_MODULES and len(parts)>=3 and parts[1].isdigit() else 2
    return ' '.join(parts[:count])
