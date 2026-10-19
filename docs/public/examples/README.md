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

首页复用下列历史 PNG，字节与 v0.1.2 源码标签一致。图中版本号均为 v0.1.1，不能当作发布包当前外观或新功能验收。

| 图片 | 日期与性质 | 固定来源 |
|---|---|---|
| SCG 飞控硬件页 | 2026-10-01；示例配置工程界面 | [原图](https://github.com/aleistercrowleybeast666/SilverStar/blob/v0.1.2/docs/GSHC/gui_layout_20261001_v1/scg_native/zh_CN_flight_hardware.png) |
| GSHC 飞行页 | 2026-10-01；未连接设备；数值由界面测试构造 | [原图](https://github.com/aleistercrowleybeast666/SilverStar/blob/v0.1.2/docs/GSHC/gui_layout_20261001_v1/delivered_zh_CN_1536x816_scale1_flight.png) · [测试脚本](https://github.com/aleistercrowleybeast666/SilverStar/blob/v0.1.2/docs/GSHC/gui_layout_20261001_v1/reproduction/gshc_layout_capture.py) |
| FLP 概览 | 2026-10-08；真实静态台架记录 `000044`；选择离线复算源 | [原图](https://github.com/aleistercrowleybeast666/SilverStar/blob/v0.1.2/docs/evidence/static_log_file_20261008/results/p44/overview.png) |

截图和示例均独立于 0.1.3 开发功能。更多硬件和算法范围见[支持矩阵](../SUPPORT_MATRIX.md)；日志/解码包身份见[精确匹配契约](../FLP/Decoder_Profile_Package.md)。

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

The home pages reuse historical PNGs whose bytes match the v0.1.2 source tag. All show v0.1.1; they are not current release captures or acceptance evidence for new features.

| Image | Date and data | Pinned source |
|---|---|---|
| SCG Flight Hardware | 2026-10-01; an example configuration project | [Original](https://github.com/aleistercrowleybeast666/SilverStar/blob/v0.1.2/docs/GSHC/gui_layout_20261001_v1/scg_native/zh_CN_flight_hardware.png) |
| GSHC Flight | 2026-10-01; disconnected; values constructed by a UI test | [Original](https://github.com/aleistercrowleybeast666/SilverStar/blob/v0.1.2/docs/GSHC/gui_layout_20261001_v1/delivered_zh_CN_1536x816_scale1_flight.png) · [Test script](https://github.com/aleistercrowleybeast666/SilverStar/blob/v0.1.2/docs/GSHC/gui_layout_20261001_v1/reproduction/gshc_layout_capture.py) |
| FLP Overview | 2026-10-08; real static bench record `000044`; offline recomputed source selected | [Original](https://github.com/aleistercrowleybeast666/SilverStar/blob/v0.1.2/docs/evidence/static_log_file_20261008/results/p44/overview.png) |

The screenshots and samples are independent of 0.1.3 development features. See the [support matrix](../SUPPORT_MATRIX.md) for hardware and algorithm boundaries, and the [exact matching contract](../FLP/Decoder_Profile_Package.md) for log/decoder identity.
