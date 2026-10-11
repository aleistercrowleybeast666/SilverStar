# 已存在的第三方修改记录

本次只补文档、许可副本与来源映射，未新增或修改以下程序。源 SHA256 和官方文件 SHA256 见 [source-map.json](source-map.json)。这些说明保留上游条款，不将第三方改成第一方 Apache。

- F1 flight `stm32f1xx_hal_i2c.h`：现有 per-handle `PlatformI2cDeadline` 与 `BlockingMemoryOwner` 字段及本地 include，原文件已有 SilverStar 修改注释。
- F1 flight `stm32f1xx_hal_i2c.c`：现有 blocking-memory 事务统一截止时间、锁/错误路径、断言 include；原文件已有 STM32Cube FW_F1 V1.8.7 适配说明。相对官方 HAL v1.1.10 共521行 unified diff（含上下文/文件头）；不把该差异数量当安全证明。
- F1 flight `stm32f1xx_hal_sd.c`：现有 HCLK-derived initialization divider 与 transfer clock 校验，替换固定118；原文件已有版本和修改注释。相对官方 HAL v1.1.10 共41行 unified diff。
- F407 `startup_stm32f407xx.s`：已存在 CCM initialized data 搬运，以及 DMA/CCM BSS 清零与 linker symbol 扩展；相对官方 CMSIS device F4 v2.6.11 共81行 unified diff。未改 CPU/IRQ 行，也未重新验证固件功能。
- C071 `Reviewed` 的 usbd_core.c/usbd_ioreq.c/usbd_cdc.c：与 v2.11.5 不同；包中已有对应 Patches/*.patch。这里仅标记派生来源与现有 SLA0044 的范围，不重试、绕过或补做受阻安全审查，不赋予“已审”含义。
- C0 平台 `usbd_cdc_if.c`：已有 bounded byte stream/LL recovery 适配注释；首次导入 commit `838f148059020b05d0de4a735332abf830f8b953` 的官方原件/manifest链已确认，适配字节未变；保留 Applications SLA0044，不声称与原件相同。
- 其余38个 board 生成文件的用户代码区/生成差异尚无准确原始模板比对，未编造完整修改清单。
- vendor 来源匹配的 CRLF/LF-only 文件只做换行分类，源程序字节保持本次前状态；六个既有 LICENSE.txt 是包装内回退说明文件，不能称为上游同名完整 LICENSE.md 的逐字节副本。

- F1/F4 HAL配置头：已记录相对各自官方配置模板的宏/模块选择、值、USER区及格式差异，保留相应 BSD 许可。
- F4 syscalls.c/sysmem.c：与 ST CubeMX 内原始资源逐字节相同，无本地内容修改；本次只附原始 SLA0048 文本与来源映射。

- SX1280lib：用户确认来自亿佰特官方原包并做过本地修改，修复了多处致命问题；未逐一穷尽扫描，不编造完整改动清单。原包无独立 LICENSE，保留 Semtech 2016 头。未来完整 SilverStar 实现尚未落地。
