# Generated Code and Project Ownership

## 当前配置与版本

产品版本是 0.1.2；SCG 工程格式 14/15/16/17 保持各自兼容边界，四档预设使用 17；decoder/project-semantics 为 1.2，旧 1.1 拒绝。算法实际参数位于 Navigation Configuration，保留 actual values、单位、representation 和共享参数约束。产品版本不机械改写独立插件、协议或已有用户工程身份。

详细参数见[参数契约](ALGORITHM_PARAMETERS.md)，界面流程见[应用说明](APP_README.md)。



## Storage repair ownership and migration

SS0.5 builtin FatFs Target glue contains FCCG-owned SDIO integrity overlays; Storage/LogSink remain
single-instance Device implementations. Reference re-import restores these controlled files and
the Logger/Host fixes. Their generated copies become project-owned as usual: normal Apply preserves
them, so existing projects require a fresh output or an explicit source port and rebuild.

Generated Host tests include `Tests/Host/storage_integrity/run_storage_integrity.py` when the
default SS0.5 SDIO/logging sources are selected. It writes only below `build/FCCG/Host/Tests`.
`Tools/sslog_audit.py` is an offline check; Generate and firmware `all` never invoke it.
`Tests/Target/storage_integrity.c` is bench-only and excluded from the production graph.
Imported custom CubeMX snapshots remain user-owned: they must port/validate an equivalent arbitrary
byte-buffer contract, including handle routing and memory accessibility; copying an `.ioc` alone
does not establish storage integrity. F407 has no DCache; this is not H7 cache validation.

## Output model
生成项目是独立源码工程，生成后可脱离FCCG构建。

```text
<Project>/
  SilverStar.ssproject
  Generated/
  APP/ / System/ / Algorithm/ / Devices/ ...   project-owned component sources
  HardwareGenerated/STM32CubeMX/
  Makefile / Targets/
  .vscode/ / .eide/
  <Project>.ssdecoder                 only when logging enabled
```

## Ownership
- Component payload首次物化后归项目所有，普通Generate不覆盖；
- `Generated/`、descriptor、build/editor metadata由FCCG管理；
- 禁用组件可保留文件但离开SourceGraph；
- `.ssdecoder`只在Logging启用时存在，Logging None时FCCG安全移除自己管理的decoder artifacts。

## Generated glue
包含：resource binding、device instance facade、capability routes、protocol selection、feature macros、project semantics、decoder identity等。Generated不包含运行期动态插件。

## Verified Board
Board插件的`connections.json`决定logical ID；`.ioc`/generated header只解析physical alias。生成后Platform Resource Closure Check验证Project assignment→logical ID→Board alias→physical symbol→platform table完全闭合。

## `.ssdecoder`
固定成员：`manifest.json`、`record_catalog.json`、`project_semantics.json`、`checksums.sha256`、`README.md`。它是纯数据ZIP，不执行代码。Package/semantics当前为1.2（不兼容1.1），SSLOG container为0.0。

完整`docs/platform/`留在FCCG仓库，不复制到每个生成工程；生成工程摘要继续使用既有README/配置摘要机制。Calibration行为见[共同契约](AIR_CALIBRATION_CONTRACT.md)。

## Shared actual values

Shared GUI values do not create runtime objects. Each declaration still emits its own compile-time macro: Pure INS uses `SYSTEM_INS_GRAVITY_MPS2` and KF6 uses `SYSTEM_KF_GRAVITY_MPS2`, with identical resolved float32 values. `project_algorithm_parameters.h` remains included through `project_flight_config.h`; no parser or heap use is added.
