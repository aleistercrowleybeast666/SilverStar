# 第三方来源与许可材料（0.1.2 后续本地候选）

根 Apache-2.0 只覆盖原创 SilverStar 材料。本目录保留已经核实的上游原始许可正文和文件来源，不改变任何第三方条款，不宣称全包是 Apache 或全包已获公开分发放行。`v0.1.2` 仍指向原源码候选；这些补充属于其后的独立提交和独立后缀候选包。

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

## 仍未闭合的具体来源材料

1. **Semtech SX1280lib**：五个源头引用的 `LICENSE.TXT` 仍缺；25 文件完整清单及候选官方证据见 source-map.json。ARM 官方镜像具有相同 Semtech 头，但不是本地完整文件的逐字节匹配来源，也没有找到这批内容的对应 LICENSE.TXT。Semtech 官方 gateway 仓库的许可不被借用。需要原始 SX1280Lib 官方导出/归档（含完整许可和 rangingCorrection 数据表）或准确原始 revision/URL。未知并不等于已证实禁止分发，当前也不能报告缺口已关闭。
2. **38 个 board 生成文件**：两份随包 `.ioc` 已明确 CubeMX 6.15.0/DB.6.0.150，以及 F1 1.8.7、F4 1.28.3；[F1 官方组件表](ST_CUBE_F1_1.8.7_COMPONENTS.txt)与[F4 官方组件表](ST_CUBE_F4_1.28.3_COMPONENTS.txt)原样保留。它们不能替代每个生成模板的许可证明。安装目录的 BSD_License.ftl 与 Ultimate_Liberty_License.ftl 都产生相同外置 LICENSE 头，因此仅凭头部不能选择 BSD 或 SLA0044。需要原始生成工程所附 LICENSE/适用模板条款；剩余38条路径已标记未解，未猜测授权。



## 本次独立核对补足的五项映射

- F1/F4 `Core/Inc/stm32f*xx_hal_conf.h`：分别来自已固定 HAL 1.1.10/1.8.5 配置模板，记录模块选择、宏值、USER区及格式差异，适用前述各自 BSD-3-Clause。它们是有证据的配置派生，不是逐字节原件，也不声称完整重现 CubeMX 渲染。
- F4 `Core/Src/syscalls.c` 与 `sysmem.c`：与安装的 ST CubeMX `templates/syscalls.c`、`templates/sysmem.c` 完全相同；适用[完整原件 SLA0048 Rev4/March 2018](STM32CubeMX_6.15_SLA0048.pdf)。保留 ST 原条件及用途范围；不采用工具内第三方 Apache 依赖的 LICENSE，也不把这份许可扩张至其余未核实模板。
- C0 平台 `usbd_cdc_if.c`：首次导入 commit `838f148059020b05d0de4a735332abf830f8b953` 同时引入适配、固定 revision 的官方 App/Target 和 companion manifest；当前适配字节从首次导入以来未变。原件 hash、现有修改声明与 manifest 链已确认，映射到现有 Applications SLA0044。它是有记录的本地派生，无需再向用户索取这一个文件的原始版本，也不表示 USB 安全验收。

五项的工作区/提交字节摘要、原件摘要、依据及27个独审产物的清单摘要见 source-map.json。HAL两配置头工作区 CRLF 与 Git/包内 LF 不同，已分别记录，未修改代码。此前六项 CMSIS/startup/system 映射仍保留；49个分拆项现仅38项待来源。

## 停在一次来源资料请求

请告诉我们 **Ground_Station0.5、Flight_Controller0.5 旧工程和 SX1280lib 最初从哪里取得**，或提供原始工程/库压缩包，保留随附许可文件即可；无需另行整理法律清单。

已提供的 FINAL 工程在独审所查许可范围内，只找到 HAL/CMSIS/FreeRTOS 条款，未找到生成模板根许可或 Semtech LICENSE.TXT。当前仓库已有 `.ioc` 和导入历史，足以确认工具/FW版本，但还不能自动关闭剩余38个 board 文件和25个 Semtech 文件。后续停在待用户来源，不继续泛化调查，也不擅删驱动。

原工程 LICENSE 是一种证据，不是唯一强制材料；匹配的权威模板/分发条款和来源、或厂家针对这些文件的明确说明，也可用于补足映射。未知不等于整个项目非法，也不能标为全部已闭合。

第一方准确权利人署名是 owner review 待办，不是本次已证明的公开禁令；根 LICENSE 不改，也不从 Git 作者猜权利人。FreeRTOS MIT、Bosch BSD、FatFs 原头继续保留（F1 flight 的 FatFs 为 R0.11，F4 为 R0.12c）。Python/Qt 二进制、EXE和安装器未进入源码 ZIP，其未来许可审计另属范围。

[已存在修改的明确记录](modifications.md)。公开分发仍未执行；所有未解项保留，未删驱动规避缺口。
