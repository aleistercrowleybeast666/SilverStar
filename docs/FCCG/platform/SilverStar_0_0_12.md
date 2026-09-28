# SilverStar 0.0.12 平台规范

SilverStar 0.0.12 是首次公开发布前的 FCCG-centered 平台冻结候选。FCCG 是中央配置、组件装配、接口冻结和版本权威；生成固件是独立可构建工程，外部参考固件仓库仅作为只读 provenance/source，不是当前平台规范的第二真相。

## 当前已验证基线
- MCU/Target：STM32F407VET6 / `SilverStar_F407`；
- Board：SS0.5 verified Board；
- OS：FreeRTOS 11.3.0，静态任务/静态内存；
- Device：JY901B、NEO-M9N、E28-2G4M12SX/SX1281、SD/TF(SDIO+FatFs)、输入电压、Mission outputs、indicators；
- Protocol：AIR M0、Serial Maintenance 0.0、SSLOG 0.0，三槽均可独立关闭；
- Decoder package：`.ssdecoder` 1.2（拒绝1.1），Project Semantics 1.2；算法参数为实际值；
- Algorithm/logic：Calibration、Alignment、Coning2/Sculling2 INS、KF6、Deployment、Landing。

## 0.0.12 关键边界
1. **Verified Board** 固定 logical→physical mapping；`.ioc`/generated defines只解析和验证physical alias，不能按扫描顺序重排Platform ID。
2. **多实例**：官方JY901B/M9N/SX1281允许同插件最多4实例，资源、driver state和native log均独立。
3. **最小source availability**：IMU只在Calibration/Alignment前选择并锁定；GNSS按liveness单向failover；AIR active telemetry在连续10次真实TX timeout后单向failover，无备用则持续有界重试。
4. **Calibration**：OneFace/SixFace是可选采样procedure，NONE始终可用。无采样procedure时启动/Reset自动NONE/Identity/READY；有采样procedure时GSHC仍可显式`CAL_START(NONE)`选择默认校正。
5. **Runtime safety**：生产初始化包含System Indicator；Alignment heavy process由FlightTask推进；Arm GNU stack-report覆盖静态任务预算。
6. **日志**：`CALIBRATION_RESULT`始终是实际有效correction快照；多实例通过physical/source descriptor区分；`.ssdecoder`只包含数据，不执行代码。

## 文档导航
完整清单见 [`details/DOCUMENT_LIST.md`](details/DOCUMENT_LIST.md)。历史0.0.7~0.0.9位于 [`history/`](history/)。数学说明位于 [`formula/`](formula/)。
