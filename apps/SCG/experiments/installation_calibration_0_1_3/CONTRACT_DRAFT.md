# 安装采集与完整 SSIC 草案：接入前字段收尾

2026-10-19 更新：用户已选每面一次操作、目标自动连续 TRAIN→HOLDOUT；正式会话/样本权威已迁至 `contracts/installation_calibration_v1.json`，GSHC 持有运行时实现。下文 WINDOW 手动分段为历史草案，不是当前默认流程；SSIC kind 2–8 仍未正式采纳，应用/保存继续禁用。相邻两段不声明统计独立。

2026-10-18；owner：`installation_calibration_B0_B2a`。机器描述为本目录 `protocol.py` / `ssic_draft.py`，是隔离草案，尚未注册到 `contracts/` 或生产能力。保留维护 0.1、SSIC schema 1、原有 MAG kind 1 和所有旧命令；不新增传输版本。新增 kind 号仅为提议，不表示已分配发布。生产 GUI/固件/TF 均未改动，应用禁用不解除。

## 线上窗口与留出

每条仍 ≤191 bytes、≤5 tokens，回应/事件 ≤511 bytes：

```text
INSTALL WINDOW <sid> <rid> <stage>:<face>:<split>:<window>:<pose>:<attempt>
INSTALL DO <sid> <rid> WINDOW_STOP
INSTALL DO <sid> <rid> WINDOW_CANCEL
INSTALL DO <sid> <rid> CAPTURE_DONE
```

`stage=MAG_ROTATE|SIX_FACE|SUPPLEMENT`；`face=NA` 仅用于磁旋转，静态为 XP/XN/YP/YN/ZP/ZN；`split=TRAIN|HOLDOUT`；window/pose 各 1–16 ASCII token，attempt 为 1..65535。窗口名全会话唯一；同一姿态可有不同窗口/split，已受理标签不可事后改写。先声明窗口，再开始采样，重复同 rid 不重复采集；任何当前源/内参变化均不得悄悄续窗。

MAG 窗口从 IDLE/MAG_FIT 开始，结束回 MAG_FIT（只表示采集结束待 PC 拟合，不表示内参有效）；SIX_START 后进入 FACE_WAIT。SIX_FACE 窗口结束回 FACE_WAIT，只有完成的 TRAIN 六面设置面 mask；HOLDOUT 不设置 mask、不参与任何内参拟合、外参优化或候选选择。CAPTURE_DONE 明确冻结批次，在 TRAIN mask=63 且至少三个完成的静态留出窗口后进入 SOLVE；不会在最后一面自动猜测结束。PC 数学门禁仍可拒绝该批次。

NEED_SAMPLES 允许同面换朝向的 SUPPLEMENT，结束仍回 NEED_SAMPLES，补完后再显式 CAPTURE_DONE。无需用户量角，不要求精确斜放。WINDOW_CANCEL 只取消当前窗口并保留原始档案/已完成窗口，磁窗口回 IDLE，普通六面回 FACE_WAIT，补采回 NEED_SAMPLES。全会话 CANCEL 停止采样/上传，PENDING 与 cleanup_complete 分开；断连不会阻止已受理取消清理，模型的 cleanup deadline 为 500 ms。其他断连保持 UNKNOWN，租约结束停止并回收，不自动恢复业务。

原始档案明确保存 selected_sources、完整源描述、每个 source sample、owner_us、窗口起止时间、窗口结果、配对号及两个原始记录索引。Archive_Import 重新校验描述 hash、源索引、窗口/时间/序列/容量和完成窗口的一对一配对；失败/取消数据保留但不进入静态拟合。返回不可变 JSON 字节及内容 digest，可直接重建数学 RawPair。MagTrainingSamples 只返回完成的 MAG_ROTATE/TRAIN，拒绝借留出数据“补足”拟合数量。训练/留出摘要独立，完整档案摘要还覆盖磁旋转、失败/取消事实及窗口元数据。

**待决定的用户流程**：留出窗口是在每面连续采一个独立时段，还是收齐六面后复访指定面。两种均可用上述字段表达；测试脚本只是一种可执行示例，不确定产品默认节奏。相同姿态留出只能检查重复性，不能解除几何多解。

## 完整 SSIC 组件

每条 SSIC record 不超过既有 512-byte 对象边界，均使用原来的 32-byte little-endian 头：magic/schema/kind/algorithm/coordinates/descriptor/physical/instance/reserved/config_u32/driver_hash/model_hash/parent_crc。reserved 保持零；driver/model 名字按生成器 `_StringCrc32_Get` 的 UTF-8 CRC32（草案限制 ASCII 子集）。config_u32 必须显式来自 owner，原型默认 0 仅为未知/合成占位，不能据此宣称真实工程绑定。头部短摘要不能代替完整 SHA-256 依赖。

草案新 kind 的 algorithm=1，coordinates=1(IMU)/2(MAG)，含义限定于这些新 kind，不能更改旧 kind 1 的坐标含义。字符串固定 ASCII、零填充；所有浮点为有限 little-endian binary64；整数位宽与 struct 一致。精确字段次序由 `ssic_draft.py` 的固定 struct 定义，未知 kind/长度/标记/非规范填充拒绝。

| 提议 kind / 件数 | record bytes | 内容与依赖 |
|---|---:|---|
| 2 IDENTITY ×2 | 321 | role、板身份（UNKNOWN 如实保留）、driver/model、完整配置标识、原始 frame；endpoint 数字 ID 在头中 |
| 3 PROVENANCE ×2 | 465 | 身份 record SHA-256、boot、坐标与时钟来源、采集内参 ID/代次、provider 校正来源、epoch/stride/时间位宽/饱和、已做轴映射、单位和软件校正层 |
| 4 INTRINSIC ×2 | 326 | 身份及来源 SHA-256、非零代次、标定 ID、输出 frame、bias、完整 3×3 matrix、IMU 静态 gyro bias/MAG reference；模型为加计对角或磁 SPD，gyro scale 未估计标志为 0 |
| 5 EXTRINSIC ×1 | 385 | 两个身份 SHA-256、两个精确内参 record SHA-256/代次、R_AM、s、R_GA 可用标记/矩阵及来源；未知 R_GA 用零存储且不输出 R_GM |
| 6 POLICY ×1 | 256 | 算法 ID、PROVISIONAL_SYNTHETIC_ONLY、完整 Policy 数值，包含搜索预算/seed/质量门限；整数项严格恢复为整数 |
| 7 QUALITY ×1 | 294 | 数学原始记录、TRAIN、HOLDOUT、POLICY、EXTRINSIC、拟合 context 的独立 SHA-256；奇异值/残差/样本数；全局唯一、坐标、硬件门限、gyro scale、应用全部 NOT_PROVEN/禁用，留出仅验证标志固定 1 |
| 8 MANIFEST ×1 | 449 | sid、expected base generation、candidate generation=base+1、事务起始 UPLOAD rid、完整原始档案 SHA-256、完整 binding SHA-256、9 件规范顺序的 kind/role/长度/SHA-256 |

整包为首件 MANIFEST + 九件组件，逐件前缀 uint16 length；顺序为 8、2/IMU、2/MAG、3/IMU、3/MAG、4/IMU、4/MAG、5、6、7。本草案实长 3628 bytes；总上限 5140 bytes、10 件，解码不递归。子对象以完整字节 SHA-256 绑定；旧父 CRC 字段同时保留用于快速检查。缺件、重复/错序、换端点、换配置、代次/内参 hash 变化、档案或 split 变化均拒绝，不能拼出部分成功快照。

更正语义固定为 `new_matrix * (provider_physical_before_software_correction - new_bias)`，整套替换旧 correction，不把新 matrix 乘在旧 correction 后。采集时内参 provenance 与本次拟合的新内参分别保存；若使用新内参，其代次须恰为当前+1，外参必须引用该新组件的精确字节。目标当前内参/轴配置/来源变化使 binding 和相关外参失效，保留数据后重算重验，不能沿用旧矩阵。R_GM 只可在已声明 R_GA 时按 R_GA·R_AM 得到；静态六面不因此变成完整陀螺尺度标定。

## 有界上传与角色

```text
INSTALL UPLOAD <sid> <rid> <total_bytes>:<CRC32_8HEX>:<sha256_64hex>
INSTALL PUT <sid> <rid> <offset>:<up_to_48_bytes_HEX>
INSTALL DO <sid> <rid> UPLOAD_CANCEL
```

UPLOAD 只在已停止采集的 SOLVE/NEED_SAMPLES/CANDIDATE_ONLY 声明单个对象集；声明中 rid 是 manifest 的事务键，不是未来 SAVE ACK。声明最多 5140 bytes，随后 PUT 每块 ≤48 bytes；相同块重试接受，冲突内容拒绝。不同声明须先 UPLOAD_CANCEL，不偷偷丢掉旧暂存；不完整/摘要错误/依赖错误不发布候选。末块在私有副本完成整包结构、配置、binding、基准、父内参和档案验证后才一次发布“结构候选”。UPLOAD_CANCEL 清空暂存、失效快照，保留源档案和会话 owner；全会话取消/超时亦回收暂存。rid 为单调非零 uint32，仅缓存最近操作，旧 rid 不循环执行。

CANDIDATE STATUS/READ 对已完整上传对象显式返回 format=SSIC_DRAFT、冻结 snapshot/sequence/length/SHA-256、每块 CRC；原有诊断 JSON 路径仍是诊断。变更/过期即 STALE。ACTIVE/SAVED 仍无持久化模型，不编造生效角色。VALIDATE/APPLY/SAVE 始终 NOT_PROVEN，即便结构和 PC 数值门禁通过；candidate generation 不是已提交 TF generation。未来 TF 需全部组件写入/读回后最后提交 manifest，事务键、CAS 基准和恢复语义须由 TF owner 正式实现。

## 最小接入清单

1. 坐标/TF owner 审核 kind 分配、config_u32/名称 hash 和完整组件头，在 `contracts/` 建立唯一机器合同/golden；本目录草案不能自行成为第二权威。
2. 采集 owner 提供真实 boot/epoch/时钟不确定度/stride、原始物理量与校正层、有限静态队列及窗口边界；真实带宽、RAM、栈和 drain 预算仍待生成/编译验证。
3. GSHC 单 reader/worker 接 WINDOW/CAPTURE_DONE、原始档案回放及分区；产品留出交互节奏经用户决定，质量不足优先同面补采。
4. 目标生命周期/配置 owner、LoggerTask 和 TF 原子事务接入后，才分别审查验证、应用、保存和断电恢复；在此之前保持应用禁用。实际 ARM/Host/power10/analyzer/栈/硬件证据均未由离线测试替代。

验证命令（无新目录，使用未占用前缀）：`python -B apps/SCG/experiments/installation_calibration_0_1_3/verify.py --run contract12 --flat`。源码以精确 bytes-hex 快照保存在既有任务目录，结果/日志/原始档案/清单同前缀保留；失败不覆盖。完整执行结果见 [CONTRACT_RESULTS.md](../../../../.work/dev013_installation_calibration_20261018/CONTRACT_RESULTS.md)。
