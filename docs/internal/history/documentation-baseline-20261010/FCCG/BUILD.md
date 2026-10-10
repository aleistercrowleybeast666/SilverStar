# Build and Development Environment

## Build truth
生成项目只使用Resolved SourceGraph。Make、EIDE、VS Code共享sources/includes/defines/linker/CPU/FPU/library/forced-include信息，不允许各自扫描源树。

当前已验证MCU插件声明`SilverStar_F407` Target Profile；该值来自MCU/Platform manifest，不是Python全局默认。

## Arm GNU
- Release：`-O2 -g`；
- Debug：`-Og -g3`；
- 保留运行时assert和静态分配；
- 输出ELF/HEX/BIN/MAP；
- first-party使用严格warning策略。

常用目标：
```text
all / clean / clean-all
host-tests
architecture-check
power10-check
static-analysis
artifact-check
stack-report
```

所有Arm GNU C编译生成stack-usage信息。`stack-report`把`.su`、ELF call graph和保守context reserve结合，对所有启用静态任务检查预算；不能用Host测试替代STM32任务栈证明。

## EIDE / VS Code
EIDE与VS Code从同一SourceGraph渲染。FCCG不生成已验证flash按钮；模板保留的OpenOCD/J-Link结构不构成烧录能力声明。

## Tool separation
- Arm GNU：固件编译/静态分析；
- GNU Make：构建编排；
- Host GCC：电脑端Host tests。
缺失工具只禁用依赖操作，不阻止Generate。

更多平台构建边界见 [`platform/details/BUILD_AND_TARGETS.md`](platform/details/BUILD_AND_TARGETS.md)。

默认生成Release配置。构建输出仅位于`build/FCCG/`，Host测试使用`build/FCCG/Host/Tests`。`stack-report`通过生成Make显式运行，需要Python作离线分析；普通固件编译不运行Python生成器。
