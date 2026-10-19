# 无需硬件体验与示例日志

[返回首页](../../../README.md) · [English](#english)

下载并完整解压 [v0.1.2 Windows 便携包](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2)。SCG 可浏览配置和生成入口，GSHC 可在未连接时浏览界面；FLP 可用下面的真实台架记录体验日志分析。

## 下载一组精确配对输入

以下文件已经保存在公开的 **v0.1.2 源码标签**中，链接固定到该标签；不需要下载整个仓库。它们不在 Windows 便携包内。记录来自 2026-10-08 的静态台架，解码包标识固件版本为 **0.1.1**，不是 v0.1.2 固件采集或火箭飞行数据。

| 文件 | 大小 | 下载 |
|---|---:|---|
| 记录 `000044` · `flight.sslog` | 885023 字节 | [原始日志](https://raw.githubusercontent.com/aleistercrowleybeast666/SilverStar/v0.1.2/docs/evidence/static_log_file_20261008/inputs/missions/000044/flight.sslog) |
| 记录 `000045` · `flight.sslog` | 878123 字节 | [原始日志](https://raw.githubusercontent.com/aleistercrowleybeast666/SilverStar/v0.1.2/docs/evidence/static_log_file_20261008/inputs/missions/000045/flight.sslog) |
| 两份记录共用 · `KF6_Static_20261008_f045d8c.ssdecoder` | 144321 字节 | [精确匹配解码包](https://raw.githubusercontent.com/aleistercrowleybeast666/SilverStar/v0.1.2/docs/evidence/static_log_file_20261008/inputs/KF6_Static_20261008_f045d8c.ssdecoder) |

浏览器直接显示解码包文本时，使用“链接另存为”保留 `.ssdecoder` 后缀。两份日志原名相同，请分别存入 `000044/` 和 `000045/` 目录；先下载其中一份和解码包即可。

1. 启动 `FLP.exe`，使用打开日志入口选择 `flight.sslog`，再选择上述 `.ssdecoder`。
2. 确认日志及 Descriptor 身份匹配，查看完整性诊断。两份输入的精确匹配模式均为 `exact_generation_profile`。
3. 先选择 **Recorded**，查看概览、传感器通道与任务记录；需要比较时，再按 [FLP 指南](../FLP/README.md)进行复算。
4. 导出到新的可写目录，保留原日志和解码包。静态台架记录没有可供演示的真实飞行轨迹，缺失的定位信息应保持不可用。

Recorded 是实际记录值；Recomputed/Offline/What-if 是有各自参数和保真度边界的分析结果。缺包、身份不匹配或缺少输入时保留错误诊断，不使用替代解码器或默认值伪装为原始记录。

### 文件校验

可用 PowerShell `Get-FileHash -Algorithm SHA256 <文件路径>` 核对：

```text
000044/flight.sslog
c5f123ccc6b0390b869412f6e0a09d834999f8be621b876f43298bb5028a1fb2

000045/flight.sslog
b9b6244f0103b02d98e3389c10661043fe7f22aa84f701bd456ea255e425308f

KF6_Static_20261008_f045d8c.ssdecoder
46b449244dcfde73baa5faaa795ac496d34f097bd095824959f53210067fafe2
```

[记录 44 历史解析结果](https://github.com/aleistercrowleybeast666/SilverStar/blob/v0.1.2/docs/evidence/static_log_file_20261008/results/m44/parse_summary.json)和[记录 45 历史解析结果](https://github.com/aleistercrowleybeast666/SilverStar/blob/v0.1.2/docs/evidence/static_log_file_20261008/results/m45/parse_summary.json)保存了当时的匹配模式、Descriptor 和诊断。这里复用已提交输入，不复制或修改原始记录。

## 截图来源

首页现使用正式 **v0.1.2** 分发程序文件的真实 Qt 离屏截图，采集于 2026-10-19。所用程序文件已与正式 ZIP 核对；没有使用 0.1.3 开发界面，也没有重绘或补造数据。具体步骤见[三工具图解](../V0_1_2_WALKTHROUGH.md)。

| 图片 | 实际输入与页面 | 截图 |
|---|---|---|
| SCG 导航配置 | 已有 FINAL 项目，只读打开与查看 | [图片](../assets/v0.1.2/scg_final_navigation.png) |
| GSHC 后期处理 | v0.1.2 标签中已公开的历史 TEST_5 JSONL 会话；离线导出完成 | [图片](../assets/v0.1.2/gshc_offline_session_export.png) |
| FLP 概览 | FINAL 的 `000062` 日志及精确解码包，选择 Recorded | [图片](../assets/v0.1.2/flp_000062_recorded_overview.png) |
| FLP 曲线 | 同一 Recorded 数据源，任务开始后前 30 秒 ENU 速度 | [图片](../assets/v0.1.2/flp_000062_recorded_flight.png) |

截图中的 `000062` 与上方可下载的台架记录 `000044/000045` 是不同案例，不能交换解码包。更多硬件和算法范围见[支持矩阵](../SUPPORT_MATRIX.md)；日志/解码包身份见[精确匹配契约](../FLP/Decoder_Profile_Package.md)。

## English

[English home](../../../README.en.md)

Extract the complete [v0.1.2 Windows package](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2). Browse SCG configuration and generation entry points, or explore GSHC while disconnected. For FLP, use the real bench recordings below.

### Download an exact input pair

These files are already public in the **v0.1.2 source tag**. The links are pinned to that tag, so you do not need the entire repository. They are not included in the Windows portable archive. The recordings come from a static bench session on 2026-10-08; the decoder identifies firmware **0.1.1**. They are neither v0.1.2 firmware recordings nor rocket flight data.

| File | Size | Download |
|---|---:|---|
| Record `000044` · `flight.sslog` | 885023 bytes | [Original log](https://raw.githubusercontent.com/aleistercrowleybeast666/SilverStar/v0.1.2/docs/evidence/static_log_file_20261008/inputs/missions/000044/flight.sslog) |
| Record `000045` · `flight.sslog` | 878123 bytes | [Original log](https://raw.githubusercontent.com/aleistercrowleybeast666/SilverStar/v0.1.2/docs/evidence/static_log_file_20261008/inputs/missions/000045/flight.sslog) |
| Shared decoder · `KF6_Static_20261008_f045d8c.ssdecoder` | 144321 bytes | [Exact decoder](https://raw.githubusercontent.com/aleistercrowleybeast666/SilverStar/v0.1.2/docs/evidence/static_log_file_20261008/inputs/KF6_Static_20261008_f045d8c.ssdecoder) |

If the browser displays decoder text, use “Save link as” and retain the `.ssdecoder` extension. Both logs have the same original filename; save them in separate `000044/` and `000045/` folders. One log and the shared decoder are enough to start.

1. Launch `FLP.exe`, open `flight.sslog`, and select the decoder above.
2. Check Descriptor identity and integrity diagnostics. Both inputs match as `exact_generation_profile`.
3. Select **Recorded** first to inspect the overview, sensor channels, and mission records. Follow the [FLP guide](../FLP/README.md) when you want to recompute and compare results.
4. Export into a new writable folder and preserve the inputs. These static bench records do not contain a real flight trajectory to demonstrate; unavailable position information should remain unavailable.

Recorded means actual recorded values. Recomputed/Offline/What-if are separate analysis results with their own parameters and fidelity boundaries. Missing decoders, identity mismatches, or missing inputs retain their diagnostics; substitute decoders and defaults must not masquerade as original recorded data.

### Verify the files

Use PowerShell `Get-FileHash -Algorithm SHA256 <path>` and compare with the three hashes in the [checksum section](#文件校验). The [historical record 44 report](https://github.com/aleistercrowleybeast666/SilverStar/blob/v0.1.2/docs/evidence/static_log_file_20261008/results/m44/parse_summary.json) and [record 45 report](https://github.com/aleistercrowleybeast666/SilverStar/blob/v0.1.2/docs/evidence/static_log_file_20261008/results/m45/parse_summary.json) preserve their original matching mode, Descriptor, and diagnostics. These links reuse committed inputs without copying or changing them.

### Screenshot provenance

The home pages now use real Qt screenshots captured offscreen on 2026-10-19 from the official **v0.1.2** program files, verified against the published ZIP. They do not use 0.1.3 development interfaces, redrawn UI, or fabricated data. See the [illustrated walkthrough](../V0_1_2_WALKTHROUGH.md#english).

| Image | Actual input and view | Capture |
|---|---|---|
| SCG navigation | Existing FINAL project, opened for inspection | [Image](../assets/v0.1.2/scg_final_navigation.png) |
| GSHC post-processing | Historical TEST_5 JSONL already public in the v0.1.2 tag; offline export completed | [Image](../assets/v0.1.2/gshc_offline_session_export.png) |
| FLP Overview | FINAL record `000062` and its exact decoder, with Recorded selected | [Image](../assets/v0.1.2/flp_000062_recorded_overview.png) |
| FLP chart | The same Recorded source, ENU velocity during the first 30 seconds after mission start | [Image](../assets/v0.1.2/flp_000062_recorded_flight.png) |

Record `000062` in the screenshots is a different case from downloadable bench records `000044/000045`; their decoders must not be exchanged. See the [support matrix](../SUPPORT_MATRIX.md) for hardware and algorithm boundaries, and the [exact matching contract](../FLP/Decoder_Profile_Package.md) for log/decoder identity.
