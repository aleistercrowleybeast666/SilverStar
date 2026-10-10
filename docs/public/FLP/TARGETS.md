# FLP 0.1.2 验证与能力边界

当前正常功能、数据身份与保存/导出流程见[应用说明](APP_README.md)。源码测试名称和旧测试计数不等于本版实际执行结果；每项结果必须绑定自己的源码、输入、命令及区间。

- Production opening 必须 log Descriptor 与 exact decoder 1.2 匹配；无旧 decoder、固定 parser 或文件名猜测回退。
- 源日志/decoder 不改写；历史 run 及参数保留，保存工件严格验证，不自动数值重算。
- Recorded、Recomputed、Offline、What-if 分别呈现，缺主源输入不借其他源补值；导出采用明确来源和范围。
- EXACT 需要匹配 Golden 和干净有效输入，身份精确匹配不证明数值等价。
- GNSS 水平完成窗口阶梯与逐样本竖直积分诊断不是同统计量，不据外观判断精度。
- 本轮针对性 Python 检查和离线 GUI 烟测不是全部日志/算法/桌面 GPU 验收；没有随包真实日志或本轮新硬件结论。
- 全面 Windows 长路径支持仍未完成；内部工件路径失败应报告并保持原工程。
