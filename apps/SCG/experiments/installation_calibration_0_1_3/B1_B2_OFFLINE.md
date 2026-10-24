# B1 配对采集与 B2 会话/编解码隔离原型

日期：2026-10-18；owner：`installation_calibration_B0_B2a`。本批次沿用当前实验目录，新增 `capture.py`、`protocol.py`、`session.py`、`test_capture_session.py`，扩展本目录 `verify.py` / `pytest.ini`；没有生产注册或生产文件写入。它是可执行的接口提案，尚未成为 `contracts/` 权威合同或设备能力。

## 运行

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B apps/SCG/experiments/installation_calibration_0_1_3/verify.py --run run10
```

使用未占用的 run 名称。runner 在同一小型任务证据目录保留完整测试、源码快照、golden、版本、命令、失败和哈希；不覆盖旧结果。新增测试和原有数学测试一起运行，未跳过数学反例。实际结果及空间增量见[本批证据](../../../../.work/dev013_installation_calibration_20261018/B1_B2_RESULTS.md)。

## 已确定的模型

`SourceDescriptor` 冻结 IMU/MAG 身份、boot、epoch、原始轴 frame、右手有符号轴映射来源、物理单位、provider 校正层、采集内参 ID/代次、源时钟/不确定度来源、选取流序号步长和时间戳位宽/饱和语义。轴映射仅记录已有变换，不再次旋转。`SourceSample` 保留完整物理向量、可选原始计数/温度、源时间、目标侧接收时间和独立 PC 收包时间；PC 时间不用于配对。未知板卡/校正来源保持 UNKNOWN；未知 boot、坐标或时钟证据不允许开始合格窗口。

| 边界 | 默认 / 行为 |
|---|---|
| 源队列 / 已配对 / 原始档案 | 8 / 32 / 128；可显式配置，上限 64 / 4096 / 8192；不覆盖旧记录 |
| 窗口 | 最少 3 对，最多 64 个窗口；window/pose 最多 16 ASCII 字符；attempt 为非零 uint16 |
| 同步 | `abs(t_imu-t_mag)+u_imu+u_mag <= 2000 us`，合计不确定度不超过 1000 us |
| 超时 | 源无数据 250 ms、单窗口 10 s；源和 owner 时间倒退均拒绝 |
| 序列 | 窗口内必须按声明 stride 前进；支持 uint32 序号回绕；时间戳不擅自回绕/扩展；饱和显式失败 |
| 配对 | 两个已选输入流的一对一 FIFO 相容配对，不插值，不复用 latest；一侧缺样、偏差大或缓冲满使窗口失败 |

这些容量和时间值仅为合成原型预算，不是 MCU 预算或硬件资格。不同采样率需在采集 owner 明确选取输入流/stride；本模型不自行将高频 IMU 丢弃至低频 MAG。窗口外样本不属于本档案覆盖范围。窗口内原始故障样本在容量允许时保留；满容量的拒收有显式计数。失败/取消窗口中的历史好配对也不能进入 `StaticRecords()`，已完成窗口和全部原始档案保留。磁旋转阶段面为 NA，不能当作静态重力输入。

`WindowTag` 已支持 SIX_FACE/SUPPLEMENT/MAG_ROTATE、TRAIN/HOLDOUT、face/window/pose/attempt。六面仍是默认流程，后续补采保持指定面换朝向，不要求量角或精确斜角。物理质量和几何门禁仍由原有数学层执行。`face_mask=63` 只表示六面采集完毕，`imu_ready/extrinsic_validated/apply/saved` 均保持 0。

## 编解码与会话

复用维护 **0.1** 的 ASCII/CRLF、请求正文 ≤191 bytes、≤5 tokens；本扩展响应/事件 ≤511 bytes、块 ≤48 bytes。未增加 Maintenance/AIR/LOGFILE/SSLOG 版本。`Request_Decode` 严格实现设计文档的 CAPS、INFO、BEGIN、DO、PUT、POLL、STATUS、READ 语法。sid 为非零 32 个小写 hex，rid 为非零 uint32，binding 为 `B-` + 30 hex，snapshot 为 `S-` + 30 hex；这些 token 仅为隔离提案，不是已发布格式。

单行最大预算和通用 framing 有独立测试；超长/断流时废弃半行，等待下一个终止符，不把残片拼成命令。响应只按完整行、操作、sid、rid 匹配。`State_Decode` 要求完整状态字段；未知阶段按 UNKNOWN，缺字段或非零应用/保存/ready 声明拒绝。Capability 探测区分明确不支持和 UNKNOWN，不能由 maintenance=0.1 推断 INSTALL。当前 core 对未知 INSTALL 的实际源码模板为 `ERR INSTALL CAPS code=BAD_MODULE reason=UNKNOWN`（`SystemConsole_ErrorWrite` 和模块分派已核对）；未做设备探测。

样本使用独立 `EVENT INSTALL IMU|MAG sid=... pair=... ctx=... data=<HEX> crc32=...`，不交给旧 MAG decoder。每部分为固定 154-byte little-endian 实验负载，字段按 `protocol.py` 的 `_PART` 明确定义，包含序号/epoch/三个时间/不确定度/有效性/向量/温度/计数/窗口/阶段等；常量身份、轴、单位和内参通过冻结 binding 的 INFO 页引用。CRC 覆盖完整部分；有限重组槽只按同 sid/context/pair 重组，不拿最后一条补缺。超时、冲突、容量或配对号 gap 使重组窗口锁定，迟到数据不能恢复成“好窗口”，须另建窗口。

会话行为：

- BEGIN 冻结上下文并获取 owner；已有安装、TF 导出或配置动作占用时拒绝。INFO 页绑定身份和完整父内参，5 秒 binding 租约；不从旧连接静默沿用绑定。
- 同一 sid/rid/操作/内容重放最近结果；相同 rid 改参数为 CONFLICT；旧 rid 为 STALE；rid 不回绕。只保留最近一次变更请求，不建无界历史缓存。
- CANCEL 立即停止新样本，返回 PENDING/cleanup_complete=0；独立 owner `Process()` 完成清理后才释放资源、返回 cleanup_complete=1。POLL 返回原操作 DO 的结果，受理不等于完成。原始档案保留。
- 断线进入 UNKNOWN，禁止业务自动续跑/重试；连接恢复只允许查询/明确取消。30 秒无变更活动或 120 秒总 deadline 停止会话；不承诺重启续会话，旧 sid 查询 SESSION_UNKNOWN。持续 STATUS 查询不会延长本原型的采集租约。
- 父内参内容/代次变更清除候选和暂存、失效快照/binding，并更新新绑定的内参描述；原始档案不改。设备身份变更须新建显式绑定，不能借内参更新悄悄换源。
- 数学候选只能绑定已完成静态记录、完整内参、坐标约定和质量策略的同一 context digest。候选诊断快照包含这些上下文及最佳数值候选，分页提供同 snapshot/sequence/长度/SHA-256/块 CRC；变化或超时返回 STALE，不拼跨代次内容。
- `VALIDATE/APPLY/SAVE` 始终返回 NOT_PROVEN，包含数值通过的候选；无目标质量证据和完整事务审查时不会发布 VALIDATED/APPLIED/SAVED。没有用 `quality=PASS` 自证有效。
- ResourceGate 仅模拟共享 owner 和 LOGFILE ENTER 的导出锁存；安装取消不解除导出模式的重启要求。实际串口及文件系统互斥尚待生产接入证明。

## 明确未完成与接入点

PUT 只测试有界、不透明字节暂存、重复块、冲突、长度/CRC/SHA-256；默认返回 OBJECT_SCHEMA_NOT_FROZEN。测试通过显式 `UploadSpec` 注入声明长度/摘要，未编造完整安装 SSIC kind、首块元数据或 TF manifest。STATUS ACTIVE/SAVED 明确 NO_PERSISTENCE_MODEL；CANDIDATE READ 是诊断 JSON，不是可提交安装对象。完整安装对象头、候选提交与 ACTIVE/SAVED 角色仍须合同/TF owner 一起冻结。

模型支持独立留出窗口；当前最小 DO FACE grammar 没有编码 window/pose/TRAIN/HOLDOUT 的选择，也没有补采结束/返回求解的完整交互。测试用采集 API 直接设置这些元数据，不能宣称已有线上留出采集流程。生产接入须先冻结这部分指令，再建立 `contracts/` 唯一 authority/golden，而不是隐藏地猜测面或 split。

接入顺序：Device/Calibration owner 在现有 IMU/MAG tap 冻结源描述及时间/stride，向静态有界队列交付原始记录；共用现有六面接受/拒绝/重采事件；SerialTask 只 drain 固定预算并序列化新 INSTALL 事件；GSHC 共享 MaintenanceOwner/单 reader，把编解码/重组/求解放 worker；生命周期/全部配置入口接同一事务 gate；LoggerTask 与 TF owner 完成正式对象事务和读回。生产写集合仍以[设计文档 8.1–8.2](../../../../docs/internal/INSTALLATION_CALIBRATION_0_1_3_DESIGN_20261018.md)为准。本轮没有触碰这些接入点。

`R_AM` 继续仅表示 mag→acc；只有明确 `R_GA` 来源才能组合 `R_GM`。静态六面不估计 gyro scale，动态 gyro 保持 NOT_IMPLEMENTED。没有新增数学唯一性主张，也没有发生需要改数学假设才能推进的歧义；已有全局唯一性/现场阈值/坐标来源 NOT_PROVEN 继续保留。Python 容量模型不是 target C 静态分配、栈或 WCET 证明；固件生成、power10/Host/analyzer/ARM、真实带宽/时钟/硬件测试均未执行。
