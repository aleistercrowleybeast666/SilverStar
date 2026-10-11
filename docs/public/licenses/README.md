# 第三方来源与许可材料（0.1.2）

根 Apache-2.0 只覆盖原创 SilverStar 材料。本目录保留已经核实的上游原始许可正文和文件来源，不改变任何第三方条款，不宣称全包是 Apache 或全包已获公开分发放行。旧源码候选及其 receipt 保留历史状态；最终 tag 与 Windows 实包身份以本次最终发布 receipt 为准。

[逐文件来源、SHA256、匹配结果与未解项](source-map.json)记录本次检查源基线、官方版本、原始字节、仅换行差异及本地修改；程序、共享契约和原用户文件未改。官方 Git tree 的 blob 匹配只证明被检查文件的字节来源，不证明整个供应包或全部历史导入。

## 已确认并补入的许可材料

| 范围 | 上游版本 | 许可正文/出处 | 结果 |
|---|---|---|---|
| F1 HAL（普通、flight 两份） | v1.1.10，commit `77fbb30b7a1d02533980400083e48c559aae5a4f` | [完整 BSD-3-Clause](ST_HAL_F1_1.1.10_LICENSE.txt) | 原 LICENSE.txt 的回退说明保留；补完整条件/免责声明 |
| F4 HAL | v1.8.5，commit `b6f0ed3829f3829eb358a2e7417d80bba1a42db7` | [完整 BSD-3-Clause](ST_HAL_F4_1.8.5_LICENSE.txt) | 原声明保留，补完整正文 |
| CMSIS device F1、三份 F103 startup、Ground system 模板 | v4.3.5，commit `8a76309ed1250d817e9c888c4417171d2ba3ba63` | [官方 Apache-2.0](CMSIS_DEVICE_F1_4.3.5_LICENSE.txt) | startup/system 仅换行差异；文件映射明确 |
| CMSIS device F4、F407 startup、Flight system 模板 | v2.6.11，commit `0fa0e489e053fa1ca7790bb40b4d76458f64c55d` | [官方 Apache-2.0](CMSIS_DEVICE_F4_2.6.11_LICENSE.txt) | system 原样；startup 保留已有 CCM/DMA 初始化扩展，见修改记录 |
| CMSIS Core | ARM CMSIS_5 5.4.0/5.9.0 中对应 Core/Include 字节 | 三个 family 插件已带完整 Apache-2.0 文本 | 72 个 Core 文件原样或仅换行不同；不把 Core 版本宏当整体 SDK 版本 |
| C071 classic CDC App/Target | stm32c0-classic-coremw-apps commit `334655ed5eb719db18fa5990a5044332eeca59dc` | [完整 Applications SLA0044](ST_C071_APPLICATIONS_LICENSE.txt) | 8 个文件与官方逐字节相同，已建立路径映射 |
| C071 USB middleware 与其派生副本 | stm32-mw-usb-device v2.11.5 | [现有完整 SLA0044](../../../apps/SCG/plugins/builtin/silverstar_usb_cdc_stm32c071_mini/payload/HardwareGenerated/C071ClassicCDC/Middlewares/ST/STM32_USB_Device_Library/LICENSE.md) | middleware 原样；Reviewed 三副本保留同上游许可范围，已有修改记录 |

SLA0044 的 ST 处理器用途范围及不得把 ST 软件置于 Apache/BSD/MIT 等开源条款下的条件保持独立。这里不会给 ST 代码增加 Apache 授权。上述许可映射也不构成 USB EP0 安全审查或正常入口放行；入口继续 BLOCKED，候选继续 EXPERIMENTAL。

在 HAL、CMSIS device、ARM CMSIS_5、C071 Applications 和 USB 指定版本的完整递归文件树中未发现 NOTICE 文件；具体 ref/tree-response 摘要见 source-map.json。没有凭空新增上游 NOTICE，也不把这项检查扩大到未核实供应包。

## 用户确认的原工程与无线库来源

用户确认 Ground_Station0.5、Flight_Controller0.5 是自己开发的项目。原工程分别为 [GS_SS1 固定提交](https://github.com/aleistercrowleybeast666/GS_SS1/tree/7fe0f61142c7360f7dbae0ac0000036315631320)（含 Ground_Station0.5.ioc）和 [FC 固定提交](https://github.com/aleistercrowleybeast666/FC/tree/cc0b377ded690556d037a412a55f87fe334c42d0)。这确认第一方工程来源；ST 生成模板、HAL/CMSIS 等既有版权及许可范围仍按各自证据保留，不因项目由用户开发就改成第一方条款。38 个剩余模板项未宣称已逐一重现完整生成过程。

SX1280 无线库下载自[成都亿佰特官方原包](https://www.ebyte.com/Uploadfiles/Files/2024-2-27/20242271620496877.rar)，SHA256 `b39eef7a3077ce459a52bf10f3268174eeff2507586580d689845e92cdff39ca`。原包没有 LICENSE/license.txt；其中25个 C/H 文件保留 Semtech 2016 Revised BSD 头，属于 Mbed C++ 到 C 的移植，之后有 SilverStar 本地修改。保留原声明，不拿其他驱动 SWDR005 的 Clear BSD 条款补位，也不编造缺失的原包许可。

用户已修复多处致命问题，但没有对全部库代码完成穷尽扫描，仍可能有缺陷。完整 SilverStar 自有实现是后续计划，**本版尚未实现**。本轮按用户明确授权，准确披露来源和限制后推进发布，不继续寻找许可或换驱动；来源确认不等于全部第三方权利条件已独立核验完毕。

## 本次独立核对补足的五项映射

- F1/F4 `Core/Inc/stm32f*xx_hal_conf.h`：分别来自已固定 HAL 1.1.10/1.8.5 配置模板，记录模块选择、宏值、USER区及格式差异，适用前述各自 BSD-3-Clause。它们是有证据的配置派生，不是逐字节原件，也不声称完整重现 CubeMX 渲染。
- F4 `Core/Src/syscalls.c` 与 `sysmem.c`：与安装的 ST CubeMX `templates/syscalls.c`、`templates/sysmem.c` 完全相同；适用[完整原件 SLA0048 Rev4/March 2018](STM32CubeMX_6.15_SLA0048.pdf)。保留 ST 原条件及用途范围；不采用工具内第三方 Apache 依赖的 LICENSE，也不把这份许可扩张至其余未核实模板。
- C0 平台 `usbd_cdc_if.c`：首次导入 commit `838f148059020b05d0de4a735332abf830f8b953` 同时引入适配、固定 revision 的官方 App/Target 和 companion manifest；当前适配字节从首次导入以来未变。原件 hash、现有修改声明与 manifest 链已确认，映射到现有 Applications SLA0044。它是有记录的本地派生，无需再向用户索取这一个文件的原始版本，也不表示 USB 安全验收。

五项的工作区/提交字节摘要、原件摘要、依据及27个独审产物的清单摘要见 source-map.json。HAL两配置头工作区 CRLF 与 Git/包内 LF 不同，已分别记录，未修改代码。此前六项 CMSIS/startup/system 映射仍保留；49个分拆项现仅38项待来源。

## 本轮收口范围

此前一次来源资料请求已收到用户答复，不再停在“等待用户提供来源”。保留逐文件证据、既有模板条款及未证明的范围，不擅删驱动或改变程序。FreeRTOS MIT、Bosch BSD、FatFs 原头继续保留（F1 flight 为 R0.11，F4 为 R0.12c）。

Windows 实包将另附实际打入的 Python、Qt/PySide6/Shiboken、数值库和字体等材料；具体版本、文件范围与验证状态以实包清单为准。源码候选的旧检查不能替代新 EXE 验证。

[已存在修改的明确记录](modifications.md)。USB 安全验收、硬件与飞行验收状态不因来源补充改变。
