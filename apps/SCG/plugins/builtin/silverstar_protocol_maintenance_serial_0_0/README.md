# Serial Maintenance Protocol 0.0

Declarative SilverStar_FCCG builtin `protocol` plugin.

Reference baseline: `main` at `cc0b377ded690556d037a412a55f87fe334c42d0`. Reference-derived files retain the recorded snapshot provenance; FCCG-owned files are replayed from their declared workspace source-of-truth and identified separately in `metadata.source_origins`. Plugin payload is data and is never executed.

This plugin owns only the `maintenance` protocol category and Profile maintenance.serial.0_0. It changes build ownership and declarative metadata only; current wire/Record bytes remain unchanged.


## FCCG独立协议插件归属

FCCG将本协议作为可独立启用或设为`不使用`的单一`维护`类别插件，当前Profile为`maintenance.serial.0_0`。
System Console源码仍由Core payload承载，但只由本Profile加入Source Graph。拆分与可选状态只改变构建归属、项目锁和声明式metadata，不改变任何现有wire/Record字节。
启用时项目锁定component、version、Profile和manifest SHA-256；禁用时对应格式11槽位为`null`。`.ssdecoder`只携带数据与语义，不携带或执行解析代码。
