# SCG 0.1.2 软件边界与待验证项

已纳入的正常软件功能和专项检查范围见[根 README](../../../README.md)。当前配置、工程、插件、生成及构建入口见[应用说明](APP_README.md)。公共文档不以旧检查点勾选表充当本版全套通过。

- SCG 严格声明式 source graph、资源所有权、未知配置拒绝及用户 payload 保护继续有效。
- 首批 F103C8/C071FBP6 classic CDC 仍为 EXPERIMENTAL 私有候选；完整普通生成入口 BLOCKED。F407 TIM1/private Ground 记录不替代首批 C071 验证。
- USB EP0 独立审查没有通过结果，不称正式放行。
- 固件 PoT 为项目文本适配；critical-contract review NOT PROVEN，不能写 NASA/原始规则认证。
- 堆、栈、MSP/ISR、间接调用、库路径、WCET、存储延迟、掉电/通信和真实飞行适用性分别需要相应证据。
- 此次公共文档/打包不改程序、不连接硬件、不产生新的固件全套验收。

插件清单中的可选项表示声明的候选能力，不证明每个 MCU/资源/设备组合已构建或已实测；确切身份不匹配时必须拒绝。
