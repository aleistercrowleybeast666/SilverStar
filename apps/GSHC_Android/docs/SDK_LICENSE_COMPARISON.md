# SDK许可只读比对 — 2026-10-13

结论：属于同一个 **Android Software Development Kit License Agreement**，不是新增的Preview或独立Google APIs许可。两版并非只改日期；但**未发现待安装的2019仓库文本，比用户已批准的2026网页文本新增使用义务**。本报告保留只读比较的历史证据；父任务随后明确确认现有授权覆盖此仓库许可，现已接受并完成最小SDK安装。实际时间与文本指纹见 [接受记录](../evidence/sdk-license-acceptance.json)。

## 官方来源与组件映射

- 网页全文：[Google官方许可页](https://developer.android.com/studio/terms?hl=en)，末尾2026-04-28。它是固定入口，内容可更新，不是不可变历史版本。
- 仓库全文：[Google官方SDK仓库XML](https://dl.google.com/android/repository/repository2-3.xml)，查找 `license id="android-sdk-license"`，末尾2019-01-16。该地址固定，但仓库内容可更新。已重新获取并确认文本与上轮保存的全文完全一致。
- 暂未验证到单独、不可变的官方2019版HTML页面，不能把别的历史AOSP许可页当作本次原文。便于阅读的准确提取副本：[android-sdk-license.txt](../build/setup/android-sdk-license.txt)。来源、文本SHA256、组件引用见 [机器可核对记录](../evidence/sdk-license-comparison.json)。

| 计划安装组件 | 官方revision | uses-license ref |
|---|---:|---|
| `cmdline-tools;latest` | 23.0 | `android-sdk-license` |
| `platforms;android-36` | 2 | `android-sdk-license` |
| `build-tools;35.0.0` | 35.0.0 | `android-sdk-license` |

以上三个remotePackage都无额外dependency声明。没有选Preview、Google APIs系统镜像或其他附加包；不代表未来所有SDK组件均可自动接受。Gradle8.13不引用这个SDK许可ID。

## 全文逐条比较结果

去掉排版、章节标题与末尾日期后，2019版47个条款、2026版48个；36条相同，11条文字变化，2026新增1条。

| 条款 | 2019仓库 → 2026网页 | 分类 |
|---|---|---|
| 1.4 | Google Inc. → Google LLC，组织表述相应变化 | 契约主体名称不同，不能仅称日期/排版修改 |
| 2.2 | 点击接受 → 点击接受及/或使用SDK | 扩展表示接受的触发方式，新增方向在已批准网页版 |
| 6.3 | 无 → 可为改进SDK向Google合作伙伴分享匿名、聚合数据 | 网页版新增的数据分享表述；2019版无此条 |
| 1.2、1.3、6.2 | HTTP链接改HTTPS；补隐私政策URL | 链接更新 |
| 8.1.2、9.4、11.1、14.4、14.6、14.7 | shall改will，相关正文其余内容相同 | 措辞更新；不作法律效力等同判断 |

6.1关于收集前通知、征求同意以及拒绝后不收集的文字**完全一致**。8.1.2的RecognitionService数据处理附录两版已有相同内容，**不是新附加义务**。用途限制、知识产权、隐私保护要求、免责、赔偿、出口限制等其余对应条款未发现新增内容。[网页条款](https://developer.android.com/studio/terms?hl=en)、[仓库原文](https://dl.google.com/android/repository/repository2-3.xml)。

这是文本差异报告，不判断两份协议法律效力完全相同，也不替用户扩大授权。后续接受依据是父任务明确确认既有用户授权覆盖此准确文本，不是把子任务的异步问题视为用户答复。仅安装记录列出的组件；不预先接受其他许可。
