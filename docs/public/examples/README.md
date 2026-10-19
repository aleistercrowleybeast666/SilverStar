# 真实日志与无需硬件体验

[中文首页](../../../README.md) · [English](#english) · [三工具图解](../V0_1_2_WALKTHROUGH.md)

使用 [v0.1.2 Windows 便携包](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2)，无需连接飞控即可体验日志打开、完整性检查、轨迹和曲线。以 FINAL 的 **000062** 为主要案例，TEST_5 的 **000028** 为独立历史参考。

## 下载精确配对的输入

每个 ZIP 仅包含一份未修改的原始日志和它的 `.ssdecoder`，无需下载整个项目或仓库。样例不在程序便携包内。

| 案例 | 下载 | 解压内容 | v0.1.2 打开结果 |
|---|---|---|---|
| **FINAL / 000062** · 主要案例 | [FINAL_000062.zip](recordings/FINAL_000062.zip) · 3835025 字节 | `000062/flight.sslog`、`SS_0_5_TEST_FINAL.ssdecoder` | 精确匹配；103668 条记录；约 135.672 秒 |
| **TEST_5 / 000028** · 独立参考 | [TEST_5_000028.zip](recordings/TEST_5_000028.zip) · 9820725 字节 | `000028/flight.sslog`、`SS_0_5_TEST_5.ssdecoder` | 精确匹配；265573 条记录；约 347.784 秒 |

两份解码器不能交换。`000062` 的文件头与解码包均标记 0.1.2。`000028` 的原始文件头标记 **0.1.0**，解码包的固件/SCG 字段标记 **0.1.1**；FLP 项目信息显示解码包的 0.1.1。保留这些历史标记，不将该记录描述为 v0.1.2 固件采集。精确匹配确认日志与生成配置身份，不补足历史可执行文件的溯源证据。

## 在 FLP 中体验

1. 完整解压程序包和其中一组样例。运行 `FLP.exe`，打开该组的 `flight.sslog`，再选择同一 ZIP 中的 `.ssdecoder`。
2. 确认精确匹配（`exact_generation_profile`），先选择 **Recorded**。在“概览”检查身份、任务摘要和记录完整性。
3. 进入“飞行”，将时间窗口选为“全程”。“水平轨迹”显示 E/N 路径和相对高度；“三维回放”显示姿态与 ENU 轨迹；“速度”等页显示随时间变化的曲线。
4. 使用时间范围、缩放和回放滑块查看局部数据。需要分析比较时，再按 [FLP 指南](../FLP/README.md)运行离线复算或 What-if，并区分各自数据源。
5. 将 CSV、图表或回放等导出到新目录，保留原始日志及解码包。

两组都是历史台架、手持与抛体流程中的记录，不是火箭飞行验证。Recorded 是实际记录值；离线复算和 What-if 是独立结果。页面中的开伞、着陆标记来自该记录的任务逻辑，不代表完成真实火箭开伞试验。

### 文件校验

使用 PowerShell `Get-FileHash -Algorithm SHA256 <文件路径>`，对照 [SHA256SUMS.txt](recordings/SHA256SUMS.txt)。清单包括两个 ZIP 及其解压文件；[来源清单](recordings/manifest.json)保留文件大小、完整哈希、版本字段、生成配置身份与正式版打开结果。

```text
FINAL_000062.zip
954105bff516d2a9c558511800295fff4bbb0b08233bf4f675d2c25a84d088c0

TEST_5_000028.zip
78b2364f85853be048021586e771cb6a01147ccd214df7e67e2876c3adbe1927
```

## 截图与其他输入

[图解](../V0_1_2_WALKTHROUGH.md)使用正式 v0.1.2 程序文件与上述两组 Recorded 数据。SCG 展示设备、导航和工程生成页；GSHC 展示真实三维模型与独立 TEST_5 JSONL 会话的离线导出，模型保持未连接时的默认姿态。

较小的历史静态台架样例仍固定在 v0.1.2 标签：[000044](https://raw.githubusercontent.com/aleistercrowleybeast666/SilverStar/v0.1.2/docs/evidence/static_log_file_20261008/inputs/missions/000044/flight.sslog)、[000045](https://raw.githubusercontent.com/aleistercrowleybeast666/SilverStar/v0.1.2/docs/evidence/static_log_file_20261008/inputs/missions/000045/flight.sslog)及[二者共享的精确解码包](https://raw.githubusercontent.com/aleistercrowleybeast666/SilverStar/v0.1.2/docs/evidence/static_log_file_20261008/inputs/KF6_Static_20261008_f045d8c.ssdecoder)。它们与上述两个运动案例属于不同输入，解码器不能混用。

## English

[English home](../../../README.en.md) · [Illustrated walkthrough](../V0_1_2_WALKTHROUGH.md#english)

Use the [v0.1.2 Windows package](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2) to explore log opening, integrity checks, trajectories, and curves without connecting a flight controller. FINAL **000062** is the main example; TEST_5 **000028** is an independent historical reference.

### Download an exact pair

Each ZIP contains only one unchanged original log and its `.ssdecoder`; no complete project or repository is needed. Samples are separate from the application package.

| Case | Download | Extracted files | v0.1.2 opening result |
|---|---|---|---|
| **FINAL / 000062** · main example | [FINAL_000062.zip](recordings/FINAL_000062.zip) · 3835025 bytes | `000062/flight.sslog`, `SS_0_5_TEST_FINAL.ssdecoder` | Exact match; 103668 records; about 135.672 s |
| **TEST_5 / 000028** · independent reference | [TEST_5_000028.zip](recordings/TEST_5_000028.zip) · 9820725 bytes | `000028/flight.sslog`, `SS_0_5_TEST_5.ssdecoder` | Exact match; 265573 records; about 347.784 s |

Do not exchange their decoders. Both `000062`'s header and decoder identify 0.1.2. The original `000028` header identifies **0.1.0**, while its decoder's firmware/SCG fields identify **0.1.1**; FLP's project information displays the decoder's 0.1.1. These historical labels are preserved; this record is not described as captured by v0.1.2 firmware. An exact match confirms log/configuration identity without establishing missing historical executable provenance.

### Try FLP

1. Extract the complete application package and one sample archive. Run `FLP.exe`, open that sample's `flight.sslog`, then select the `.ssdecoder` from the same ZIP.
2. Confirm `exact_generation_profile` and select **Recorded** first. Check identity, mission summary, and integrity in Overview.
3. Open Flight and choose the Full time window. Horizontal trajectory shows the E/N path and relative height; 3D replay combines attitude and the ENU path; Velocity and other tabs show time-series curves.
4. Use the time range, zoom, and replay slider to inspect intervals. Follow the [FLP guide](../FLP/README.md) for offline recomputation or What-if comparisons, keeping their analysis sources distinct.
5. Export CSV, charts, or replay results into a new folder and preserve the original inputs.

Both cases are historical bench, handheld, and thrown-object records, not rocket flight validation. Recorded means actual recorded values; recomputation and What-if produce separate results. Deployment and landing markers come from each recording's mission logic and do not establish a real rocket deployment test.

### Checksums

Use PowerShell `Get-FileHash -Algorithm SHA256 <path>` and compare with [SHA256SUMS.txt](recordings/SHA256SUMS.txt), which covers both ZIPs and their contents. The [provenance manifest](recordings/manifest.json) preserves sizes, full hashes, version fields, generation identity, and official-version opening results. Archive hashes also appear in the [checksum section](#文件校验).

### Screenshots and other inputs

The [walkthrough](../V0_1_2_WALKTHROUGH.md#english) uses official v0.1.2 program files and both Recorded datasets above. SCG shows devices, navigation, and project generation. GSHC shows its real 3D model and offline export of a separate historical TEST_5 JSONL session; the model remains in its default disconnected pose.

Smaller historical static bench inputs remain pinned to v0.1.2: [000044](https://raw.githubusercontent.com/aleistercrowleybeast666/SilverStar/v0.1.2/docs/evidence/static_log_file_20261008/inputs/missions/000044/flight.sslog), [000045](https://raw.githubusercontent.com/aleistercrowleybeast666/SilverStar/v0.1.2/docs/evidence/static_log_file_20261008/inputs/missions/000045/flight.sslog), and [their shared exact decoder](https://raw.githubusercontent.com/aleistercrowleybeast666/SilverStar/v0.1.2/docs/evidence/static_log_file_20261008/inputs/KF6_Static_20261008_f045d8c.ssdecoder). They are separate inputs from the two motion examples above; their decoders must not be mixed.
