# Magnetometer Calibration (0.1.0 software path)

GSHC 的 **Magnetometer Calibration** 页使用飞控 Maintenance Serial 端口。常规 AIR/GSP 地面站串口仍独立运行；磁力计原始采集、应用和持久保存不经过 AIR M0。

1. 选择飞控维护 COM 端口、波特率与磁力计实例并连接。
2. 设置当地参考磁场强度，开始采集并缓慢旋转设备，使点云覆盖八个空间象限。飞控只传输新的物理单位样本，最多 20 Hz；GSHC 最多保存 4096 个样本，且采集期间必须保持同一物理设备身份。
3. 停止采集后检查样本数、八象限覆盖、参考场、RMS/最大残差、轴条件数以及硬铁/软铁结果。拟合未达到质量门限时不能应用。
4. 点击 **Apply to FC**。飞控按实例与 `physical_device_id` 验证固定 84-byte 校准对象及 CRC32，然后只应用到 RAM。此时校准尚未持久保存。
5. 点击 **Save Calibration**。GSHC 轮询 `CAL READ`；仅在飞控返回 `saved=1`、`pending=0`、非零 generation 和相同设备身份后显示保存成功。持久层使用双槽、sync、读回和 CRC 验证。

**Read Status** 显示飞控当前 generation 和物理身份；存储对象长度、CRC 或身份错误经 `load_error` 报告。**Clear FC Calibration** 停用运行时校准并持久写入 tombstone。飞控的 INS/Alignment 从公共磁力计接口获取校准后样本；原始 Maintenance Serial 样本保持原样用于采集。

该闭环已有 PC Host、F407 ARM build 和存储模拟验证。真实磁力计、飞控维护 UART 及板端持久写入仍需 Round 5 实机验证。
