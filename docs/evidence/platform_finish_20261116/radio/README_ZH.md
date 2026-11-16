# 无线选型、空选与 E19 软件边界

共享无线属性先选频段，再在同一 AirLink 模型下过滤两端模块。选择 2.4 GHz / 433 MHz 会在私有草稿中恢复该频段当前受支持的 PHY，并清除不兼容模块及其专属资源引用；确认应用才提交，取消不修改工程。只提供 LoRa。已有但不兼容的导入选择明确显示为不可用，不悄悄换型号。显式“未选择”可保存草稿，生成时仍要求所选目标满足全部依赖。

已有板卡使用内置工程生成入口，不再显示 CubeMX 导入按钮；只有自定义目标显示导入入口。两端空选均明确表达缺项，选择板卡后可以继续配置设备和资源，生成校验不因可以选择板卡而放行冲突。插件目录扫描改用每次重新检查的 scandir，继续拒绝符号链接与 Windows junction，缓存目录也不会跳过安全检查。

原目录已有六个 E28 SPI 型号。本次新增 Ebyte **E19-433M20S2**，保持 experimental / hardware-unverified。它使用内部 DIO4 收发前端，不能沿用 E32 的外部 RX_EN/TX_EN。新 owning driver 按芯片寄存器读改写及回读验证切换 DIO4，失败返回普通错误并保留既有安全停机路径；未扩展中断或运行时函数指针例外。

当前合格的软件参数仍限定为 433 MHz、SF7、BW125 kHz、CR4/5、preamble16、MTU61、芯片 17 dBm、SPI ≤1 MHz。没有把营销标称 20 dBm、整个工作频段或其他近似型号标为支持。E19 记录为 mission_radio_profile_v3 backend2/module2，E32 原 module1 保留；三个真实存储 reader、Python decoder、FLP 显示和运行设备信息接口同步识别，未知 module 仍拒绝。

来源为 [Ebyte E19-433M20S2 英文手册](https://www.cdebyte.com/pdf-down.aspx?id=885)（本地 PDF SHA256 `81390835a218d63a75c633bc6803e8e0d9fa5b805202ff555681e54b2784882c`）与 [Semtech SX1278 Rev7 数据手册](https://www.ebyte.com/pdf-down/2879.html)（`330745f933df00015d2de3efd582608339350ba3a21001d11b9d449839ce016b`）。厂商另一下载返回 WAF HTML，未将其作为 PDF 或以绕过方式采纳其他型号。

## 软件验证与保留的失败

* 原真实 C reader 拒绝 E19 的前失败为 3 failed / 1 passed；修复后业务和驱动组合 240 passed。
* 完整实际设备信息入口复核发现 E19 仍报告 E32；前失败 1 failed / 2 passed，修复后新旧型号、DIO4 正常/故障路径、三个 reader、实际 GCC analyzer 与 ARM ABI 编译组合 **249 passed**，见 `e19-final-host.log.gz`。不把 ABI 编译当完整固件链接。
* emitted architecture 检查器对正常 E32/E19 和模块号、重复宏、引脚缺失/重复、错误前端等破坏测试 **14 passed**；旧五引脚要求仍适用于 E32，E19 精确三引脚与空 sentinel 单独约束。
* SCG 当前 GUI/模型回归 **93 passed / 1 skipped**，125% / 150% 分别 3 passed。跳过项是 Windows 拒绝测试夹具创建符号链接（WinError 1314），不是通过；没有改访问控制。GUI 使用 Qt offscreen，不代表原生显示验收。
* `ux-test*`、`ux-final`、`e19-generation*` 保留早期测试夹具错误；`cache-test3` 保留并发修改 Tools 导致的真实源身份拒绝。最终结果以总报告记录的冻结后回归为准，不将这些失败隐藏。

随后独立复核发现高级 PHY 编辑后的候选刷新缺陷：不支持的频率下清空飞控，地面选择被显示为空但草稿仍保留；恢复默认后也未恢复候选。三条真实 Qt 操作前失败保存在 `radio-refresh-prefail.log.gz`。修复统一从私有草稿刷新列表，保留带禁用标记的不兼容原选择；恢复合法参数重新启用候选，不删除另一端配置。修复后的事务/界面组合 17 passed / 1 Windows 符号链接权限 skip，见 `radio-refresh-post2.log.gz`；第一次后测的唯一失败是新测试比较 Qt QVariant 的 list/tuple 表示，已保留。

扩展 15 文件回归首次为 **16 failed / 356 passed / 1 skipped**，输入封印前后无变化，完整命令、JUnit 与日志以 `root-broad-initial-` 前缀保存。16 项均为已有无线测试仍期待导出格式14/15/16，而本轮基线 `d52854c` 已统一写格式24，或把现代文档仅改版本号后先触发了 mission_process 的版本门禁。测试现明确检查当前格式，并使用仓库内真实 v14 夹具先确认可以解析、再加入新无线字段，继续要求相同的 format16 拒绝；没有改生产解析器或放宽版本校验。相应重跑结果以总报告为准，不拼接成一次未执行的全套通过。

上述旧格式断言修正后，原无线操作组继续运行到保存重开等后续步骤，出现 **1 failed / 39 passed**：一次 `StandardComboBox.model()` 返回了 `QStandardItem` wrapper，调用 `.item()` 时异常（`radio-format-post.log.gz`）。现在组合框初始化时显式创建由其拥有的 `QStandardItemModel`，并保留 Python wrapper，早于视图与滚动配置；参照 [Qt 6.10 组合框模型接口](https://doc.qt.io/qtforpython-6.10/PySide6/QtWidgets/QComboBox.html)。模型身份/条目禁用/清空/200轮 QObject 销毁、弹出滚动与候选刷新组合 **22 passed**；同一原无线操作组完整重跑 **40 passed**（`radio-format-post2.log.gz`）。新生命周期测试初稿假设非 QObject 的 QStandardItem 在清空后 `isValid()` 必为 false，实际绑定未提供该见证，改为核对真实 rowCount/count 并停止访问被移除 item；该失败日志仍保留。这些结果不等于定位了 Qt 上游根因，也不作为 OpenGL 白屏修复证据。

完整固件与严格栈另见本轮 contracts / boards 收据。早期 `.work/pf1117/e19` 的 74 Host 程序不包括最终设备身份修复，不能作为最终源码的全套验证；最终 epoch `contract-e19-a` 实际重新执行 74 程序、5,508,837 checks、0 failures，12 compile-pass、17 expected-compile-failure、23 not-applicable 与 mandatory storage4/4 均保留。输入前后无变化，命令、全部输入 SHA 及完整输出见 `e19-final-full-receipt.json.gz` / `e19-final-full-host-tests.log.gz`。独立 B 每配置504个产物与 A 相同，两配置 strict 通过。所有射频功率、前端电平、空口互通、天线、接线和 MCU 实时性仍待硬件验证。

最终冻结后完整执行 18 文件回归：**394 passed / 1 skipped**，618.98 秒（总命令 622.15 秒），exit0，SCG src/plugins、contracts 及全部所选测试前后 SHA 无变化。唯一 skip 仍为 WinError1314 符号链接权限；没有降低断言或修改权限。完整命令、所有输入 SHA、JUnit 和输出见 `root-broad-final-*`。这是已执行的 395 项组合，不是整个 SCG 仓库测试全集，也不拼接先前结果。
