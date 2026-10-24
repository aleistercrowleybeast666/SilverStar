"""Presentation only: reviewed R04 enums, raw codes retained, no inferred cause.

Sources: system_health.h, system_startup.h/.c, system_lifecycle.h,
system_calibration.h, logger_bus.h and SYSTEM DIAG in system_console.c.
"""
import re


def Text(i18n, zh, en):
    return en if getattr(i18n.language, 'value', i18n.language) == 'en_US' else zh


def MaintenanceError_Format(error, i18n):
    raw = str(error)
    if Text(i18n,'zh','en')=='en':return raw
    if 'reconnect required' in raw or 'reconnect and renegotiate' in raw:
        summary = '维护通信未完整确认，连接已失效；请断开后重新连接。上一条未完成的响应不能用于下一次操作。'
    elif 'timed out' in raw or 'timeout' in raw.lower() or 'deadline' in raw.lower():
        summary = '维护操作超时，未确认成功；请检查连接状态和下方原始诊断。'
    elif 'cancel' in raw.lower():
        summary = '操作已取消；保留已生成的目标文件和源日志。'
    elif 'Close failed' in raw:
        summary = '维护串口释放失败，请重试释放；当前不能打开第二个连接。'
    else:
        summary = '操作失败，未确认成功；请检查下方原始诊断。'
    return summary+'\n原始诊断：'+raw


_BLOCK = (
    ('配置无效','Invalid profile'), ('主IMU不可用','Primary IMU unavailable'),
    ('姿态不可用','Attitude unavailable'), ('输出尚未安全','Output not safe'),
    ('必需设备不可用','Required device unavailable'), ('启动检查未完成','Startup incomplete'),
    ('启动检查失败','Startup failed'), ('校准尚未就绪','Calibration not ready'),
    ('对准尚未就绪','Alignment not ready'), ('内部断言故障','Assertion fault'))
_DEVICES = (('输出','Output'),('IMU','IMU'),('GNSS','GNSS'),('磁力计','Magnetometer'),
    ('气压计','Barometer'),('硬件姿态','Hardware attitude'),('遥测','Telemetry'),
    ('维护口','Console'),('电源','Power'),('存储','Storage'))
_ATTITUDE = (('未知','Unknown'),('姿态就绪','Attitude ready'),('校准未就绪','Calibration not ready'),
    ('姿态源不可用','Source unavailable'),('无姿态样本','No sample'),('姿态无效','Invalid attitude'),('姿态已过期','Stale attitude'))
_CAL = (('空闲','Idle'),('等待放置校准面','Waiting for face'),('采样中','Collecting'),
    ('检查中','Checking'),('校准就绪','Calibration ready'),('校准失败','Calibration failed'))
_WAIT = (('无等待原因','No wait reason'),('无数据流','No stream'),('检测到旋转','Gyro moving'),
    ('加速度幅值不符','Acceleration magnitude'),('重力方向不符','Gravity direction'),
    ('采样方差超限','Variance'),('采样间隔异常','Sample gap'))
_LIFECYCLE = (('启动 BOOT','BOOT'),('自检 SELF_TEST','SELF_TEST'),('飞前 PREFLIGHT','PREFLIGHT'),
    ('准备 READY','READY'),('任务运行 FLIGHT','FLIGHT (mission running)'),('回收 RECOVERY','RECOVERY'),
    ('着陆 LANDED','LANDED'),('任务后 POSTFLIGHT','POSTFLIGHT'),('故障 FAULT','FAULT'))
_FINAL = (('空闲','Idle'),('已请求收尾','Armed'),('排空日志中','Draining'),('日志收尾完成','Finalized'))
_MAINTENANCE = (('未进入维护','Off'),('正在进入维护','Draining'),('维护就绪','Ready'),('维护失败','Failed'))
_REASONS = {
    'no_health_block': ('未上报健康阻塞；不代表START授权','No health block; not START authorization'),
    'not_published': ('尚未发布观测','Not published'), 'not_available': ('无可用观测','Unavailable'),
    'not_start_authorization': ('仅状态观测，不代表START授权','Observation, not START authorization'),
    'io_fault': ('已上报I/O故障，具体原因未提供','I/O fault reported; detailed cause unavailable'),
    'finalized': ('日志收尾完成','Finalized'),
    'write_completion_not_durability': ('写入完成计数，不等于持久化证明','Write completion is not durability proof'),
    'state_time_not_task_heartbeat': ('数据状态时间，不是任务心跳','State time, not task heartbeat'),
    'solution_validity_not_sensor_online': ('解算有效性，不是传感器在线证明','Solution validity, not sensor presence'),
    'ram_observation': ('RAM观测','RAM observation'),
    'sequence_changed_or_writer_active': ('读取期间序列变化或写入者仍在发布，本次快照无效','Sequence changed or writer active; snapshot invalid'),
    'completion_not_exported': ('未导出完成证据','Completion not exported'),
    'completion_not_instrumented': ('未提供完成观测','Completion not instrumented'),
}
for _reason, _labels in zip(('profile_invalid','primary_imu_unavailable','attitude_unavailable',
        'output_not_safe','required_device_unavailable','startup_incomplete','startup_failed',
        'calibration_not_ready','alignment_not_ready','assertion_fault'), _BLOCK):
    _REASONS[_reason] = _labels


def _Number(value):
    if type(value) in (int, bool):
        return int(value) if 0 <= int(value) <= 0xFFFFFFFF else None
    if isinstance(value, str) and re.fullmatch(r'(?:0x[0-9A-Fa-f]{1,8}|[0-9]{1,10})', value):
        number = int(value, 16 if value.startswith('0x') else 10)
        return number if number <= 0xFFFFFFFF else None
    return None


def _Enum(value, labels, i18n, names=()):
    number = names.index(value) if isinstance(value,str) and value in names else _Number(value)
    label = Text(i18n, *labels[number]) if number is not None and number < len(labels) else Text(i18n,'未知码','Unknown code')
    return f'{label} ({value})'


def _Mask(value, labels, i18n):
    number = _Number(value)
    if number is None:
        return Text(i18n,'未知码','Unknown code') + f' ({value})'
    found = [Text(i18n,*label) for bit,label in enumerate(labels) if number & (1 << bit)]
    unknown = number & ~((1 << len(labels))-1)
    if unknown:
        found.append(Text(i18n,'未知位','Unknown bits')+f' 0x{unknown:08X}')
    return (' / '.join(found) or Text(i18n,'无已上报标志','No reported flags')) + f' (0x{number:08X})'


def DiagnosticValue_Format(identifier, key, value, i18n):
    if identifier in ('task.preparation','legacy.system','firmware','startup'):
        if key in ('start_blocking_mask','block','blocking_mask'):
            return _Mask(value,_BLOCK,i18n)
        if key in ('warning_mask','warn','required_failure_mask','optional_failure_mask'):
            return _Mask(value,_DEVICES,i18n)
        if key in ('attitude_status','attitude'):
            return _Enum(value,_ATTITUDE,i18n,("UNKNOWN","READY","CALIBRATION_NOT_READY","SOURCE_UNAVAILABLE","NO_SAMPLE","INVALID","STALE"))
    if key in ('phase','lifecycle') and identifier in ('legacy.system','firmware','thread.logger'):
        return _Enum(value,_LIFECYCLE,i18n,("BOOT","SELF_TEST","PREFLIGHT","READY","FLIGHT","RECOVERY","LANDED","POSTFLIGHT","FAULT"))
    if identifier == 'calibration':
        if key == 'state': return _Enum(value,_CAL,i18n,("IDLE","WAIT_FACE","COLLECTING","CHECKING","READY","FAILED"))
        if key == 'wait_reason': return _Enum(value,_WAIT,i18n,("NONE","NO_STREAM","GYRO_MOVING","ACCEL_MAGNITUDE","GRAVITY_DIRECTION","VARIANCE","SAMPLE_GAP"))
        if key == 'mode':
            return Text(i18n,'未选择','Not selected')+f' ({value})' if _Number(value)==255 else _Enum(value,(('无过程','None'),('单面','One face'),('六面','Six face')),i18n)
    if key == 'finalization' and identifier in ('thread.logger','firmware'):
        return _Enum(value,_FINAL,i18n)
    if key == 'maintenance' and identifier == 'firmware':
        return _Enum(value,_MAINTENANCE,i18n)
    booleans = {
        'ready':(('未准备就绪','Not ready'),('已准备就绪（不代表START授权）','Ready (not START authorization)')),
        'writer_open':(('写文件关闭','Writer closed'),('写文件打开','Writer open')),
        'open':(('写文件关闭','Writer closed'),('写文件打开','Writer open')),
        'log_fault':(('未置日志故障标志','No log-fault flag'),('日志故障，具体原因未上报','Log fault; detailed cause unavailable')),
        'healthy':(('健康标志未通过','Unhealthy flag'),('健康标志通过','Healthy flag')),
        'mounted':(('未挂载','Not mounted'),('已挂载','Mounted')),
        'passed':(('检查未通过','Check not passed'),('检查通过','Check passed')),
        'completed':(('检查未完成','Incomplete'),('检查完成','Complete')),
    }
    if key in booleans and identifier in ('task.preparation','thread.logger','storage.tf','legacy.storage','firmware','startup','calibration'):
        return _Enum(value,booleans[key],i18n)
    return str(value)


def DiagnosticReason_Format(reason, i18n):
    label = _REASONS.get(reason)
    return f'{Text(i18n,*label)} ({reason})' if label else str(reason or Text(i18n,'具体原因未上报','Detailed cause unavailable'))


def DiagnosticState_Format(state, i18n):
    labels = {'OBSERVED':('已观测','Observed'),'WAIT':('等待','Waiting'),'BUSY':('处理中','Busy'),
        'FAULT':('已上报故障','Fault reported'),'UNKNOWN':('未知','Unknown'),'STALE':('历史观测，已过期','Previous observation, stale')}
    return f'{Text(i18n,*labels[state])} ({state})' if state in labels else f'{Text(i18n,"未知状态","Unknown state")} ({state})'


def WatchValue_Format(identifier, value, i18n):
    for prefix,group in (('System/Src/system_health.c::s_health.','task.preparation'),
            ('System/Src/system_log_file.c::s_snapshot.','thread.logger'),
            ('System/Calibration/Src/system_calibration.c::s_status.','calibration'),
            ('System/Src/system_startup.c::s_startup_report.','startup')):
        if identifier.startswith(prefix):
            return DiagnosticValue_Format(group,identifier[len(prefix):],value,i18n)
    return str(value)


def ConsoleResponse_Summary(command,response,i18n):
    from services.maintenance_commands import ConsoleCommand_ResponsePrefix
    prefix='OK '+ConsoleCommand_ResponsePrefix(command)+' '
    if not response.startswith(prefix):return ''
    group=('calibration' if command.startswith('CAL ') else
           'thread.logger' if command=='LOG STATUS' else
           'startup' if command.startswith('SYSTEM STARTUP') else 'firmware')
    values=[]
    for token in response[len(prefix):].split():
        key,separator,value=token.partition('=')
        if not separator:continue
        translated=DiagnosticValue_Format(group,key,value,i18n)
        if translated!=value:values.append(key+': '+translated)
    return ' · '.join(values)
