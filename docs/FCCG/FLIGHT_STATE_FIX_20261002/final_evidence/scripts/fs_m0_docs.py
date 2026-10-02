from pathlib import Path
import sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
p=repo/'docs/GSHC/AIR_PROTOCOL.md';s=p.read_text(encoding='utf8')
lines=s.splitlines();lines=[l for l in lines if not (l.startswith('| `0x15` | `NAV_CAPABILITY`') or l.startswith('| `0x16` | `NAV_PREPARATION`') or l.startswith('| `0x17` | `NAV_HEALTH`'))]
s='\n'.join(lines)+'\n'
paragraph=next(l for l in s.splitlines() if 'GNSS origin' in l and 'schema 1' in l)
start=s.index(paragraph);end=s.index('\n---',start)
s=s[:start]+'''本次发布以板端 M0 的真实自检、校准、对准、解锁及 system_ready / START block reason
作为 START 前置条件。GNSS 是否必需由项目和内部对准/估计器配置决定；默认可选 GNSS
保持可在无 fix / 无 GNSS origin 时运行本地 INS/Baro。GSHC 不要求 NAV 扩展或额外订阅
才能 START，也不会通过 NAV 显示状态制造 READY。板端 preparation generation 和二次
前置安全检查保持有效；缺失真实 IMU、对准或系统就绪仍阻止 START。
'''+s[end:]
heading=next(l for l in s.splitlines() if l.startswith('## 41.'))
s=s.replace(heading,'''## 41. 导航扩展 schema 1：延期，保留历史记录解码资料

2026-10-02 本次发布恢复原 M0 八种帧集合：`10/11/12/13/14/20/30/40`。
飞控不发送 `NAV_CAPABILITY (15)`、`NAV_PREPARATION (16)`、`NAV_HEALTH (17)`；
`NAV_SUBSCRIBE (0E)` 按不支持的命令返回原有 `BAD_CMD` ACK。GSHC 不自动订阅、
不提供实时 NAV 面板，也不把扩展就绪作为 START 依赖。原帧字段、编号、量化、
ACK / 关键 STATUS / FLIGHT_STATE 调度范围不变。下述格式与周期仅说明历史实验
记录，解码兼容保留，当前发布不启用这些发送周期。

ESKF_15、SF6、传感器能力、内部估计器健康、preparation generation 安全检查及
本地日志/诊断仍保留。导航详细诊断不通过 M0 发送。扩展重新发布须另行评估
实际有限半双工吞吐、控制响应和主流 FLIGHT_STATE 预算。''')
subscription=next(l for l in s.splitlines() if 'GSHC' in l and '`NAV_SUBSCRIBE`' in l and not l.startswith('|'))
s=s.replace(subscription,'历史实验在基础 Capability 握手成功后发送一次 `NAV_SUBSCRIBE`；本次发布已取消。')
p.write_text(s,encoding='utf8')
print(str(p),flush=True)
