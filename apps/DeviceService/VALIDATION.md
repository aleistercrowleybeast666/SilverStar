# 模拟原型验证记录 — 2026-10-13

范围：本目录的标准库 Python API/CLI。无真实设备、串口/USB枚举、网络连接、常驻进程、
GUI、烧录、日志删除或运动。没有对其他项目运行测试或做修改。

## 暂存目录检查

- Python：`3.14.0 (tags/v3.14.0:ebf955d, Oct 7 2025) [MSC v.1944 64 bit (AMD64)]`。
- 位置：`C:\Users\chdxm\Documents\Codex\2026-10-13\task-3\SilverStar_DeviceService`。
- 首次 `python -B -m unittest discover -s tests -v`：在执行环境重定向的临时目录上未完成，
  停在下载测试，主动中断；不计为通过。解释器输出了 `Failed to find real location` 警告。
- 仅在验证子进程中将 `TEMP` / `TMP` 设为 `C:\Users\chdxm\AppData\Local\Temp` 后，
  用 `faulthandler.dump_traceback_later(20, exit=True)` 包装相同 unittest discovery 复验：
  **18 tests，0 failures，0 errors，0 skips；0.238 s；进程退出 0**。未触发超时。
  没有修改系统/用户环境变量，原型无需这项全局配置。

## 覆盖内容

- 固定模拟枚举；真实端口/USB字符串拒绝；device/boot ID 均 unknown；不伪造 READY。
- LOGFILE v1 能力字段与 9 字节 golden 元信息；无日志能力的机械设备明确 UNSUPPORTED。
- 下载总长度/CRC32、SHA-256、不同临时目录、来源不删除、共享 manifest 关键字段及文件集合。
- 损坏/截断/超长样例和本地 I/O 故障不返回完成下载。
- 写命令/连接/删除/烧录/运动/启停采集拒绝；额外命令和路径字段拒绝；日志文本不执行。
- 租约单所有者、TTL、代次、过期、错误持有者、8 个并发申请仅 1 个成功。
- 不同对象的租约不共享，明确不能据此声称跨进程/真实设备互斥。
- CLI JSON、成功/拒绝/非法参数退出码；源码无硬件/网络/动态执行入口的窄静态检查。

测试对本原型产生的清单按共享 schema 检查关键字段、角色、路径和真实文件哈希；
不是完整 JSON Schema Draft 2020-12 验证器，不声称验证任意外部导入清单。
源码静态检查不是 Python 安全沙箱或完整安全审计。

## 过程文件与撤回

- 源码：`device_service.py`；测试：`tests/test_device_service.py`。
- `contracts/`：共享契约原文快照，来源和哈希见 README。
- `evidence/20261013-mock-v0/`：最终目录的测试输出、CLI 快照、执行摘要、源码哈希；
  所有者为本次 DeviceService 原型任务，用于复核，保留。
- `silverstar-device-service-mock-*`：仅在 OS 临时目录生成的模拟样例；不是用户原始日志。
  单测的临时样例由 `TemporaryDirectory` 管理，不拷贝到其他项目。
- 两个诊断探针的空目录位于本任务使用的沙箱临时目录和本机临时目录，名称为
  `silverstar-device-service-probe-fldbxpcu` / `silverstar-device-service-probe-uurd_037`；
  不作日志/硬件证据。未进行跨目录清理。
- 没有安装依赖、服务或凭据；没有提交、push、tag 或发布。新目录没有被其他应用引用。

未验证：真实 LOGFILE ASCII/PENDING/POLL/取消时序、硬件身份、固件生命周期门禁、
实机日志、FLP 配对解码、跨进程互斥、断线恢复、CF33/GSHC集成和任何运动安全。

## 指定交付目录复验

复制后执行的原始输出和退出码见 `evidence/20261013-mock-v0/`。结果在复制复验时追加。

Final-directory verification: unittest exit=0, tests=18, duration=0.554s; CLI status exit=0; CLI lease-demo exit=0. See evidence/20261013-mock-v0/summary.json and unittest.txt.
