# 当前交接 — 2026-10-13

最终授权范围已完成：独立Android工程统一构建、lint和本机框架回归通过，没有当前构建阻塞。未修改SilverStar、未安装手机、未连接设备、未推送/tag/发布。目录没有.git；以源码指纹和原文快照标识当前结果，不声称已提交。

## 当前产物

- [debug APK](app/build/outputs/apk/debug/app-debug.apk)：`cn.silverstar.gshc`，`0.1.3-dev.1` / code1，min26 / target36。
- 大小 **2527905字节**；SHA256 **ebd76cfd2bc0be8c566d47cfec01628aaa150d37d4558bf5ef80e108ebcacd77**。
- APK v2 debug签名验证通过；两个构建的USB开关均false。包内仅前台服务、connectedDevice、通知及AndroidX内部签名广播权限，无网络或全盘存储权限。
- [构建和14项测试明细](evidence/android-build.json)、[总验证记录](evidence/VERIFICATION.md)、[环境占用](evidence/setup-status.json)。

## 本轮实际修复

1. background捕获epoch并在worker内复核，旧生命周期回调不能停止新USB会话；主动stop保持队列语义。USB状态提交前再次在端口锁内核对lease。
2. 资源关闭串行化；Service销毁只安排I/O线程清理，等待打开/读取退出，维护口还等待exchange锁退出后才释放自身lease。拔插也保留尚在清理的占用；旧lease不能释放/失效新lease。
3. 回收站查询和选择绑定Activity生命周期、requestId及目标版本，一次消费；旋转不重置Application会话。确认按钮也拒绝旧窗口及重复回调。
4. 仅逐个解码FLIGHT_STATE采样，分片/非飞行帧不重复缓存值，多帧及相同时间戳保留源顺序；31样本实时/回放一致。
5. 框架测试发现并修复布局回调无条件setMaxLines造成的连续重排；保留原rotation/idle测试通过。修复SAF旧query调用、接收器flag和字体常量；周期任务改fixed-delay，避免后台补跑积压。

## 验证与边界

核心56、TF287、storage113、共享schema56断言通过；冻结PC152帧、31样本兼容通过。Android框架测试 **14/14**，lint **0错误/9警告**（2项依赖更新提示、7项国际化提示，未屏蔽）。最终全任务 `BUILD SUCCESSFUL in 55s`。

HTML20案例和6图是已有浏览器设计证据；未重新将它们称为原生截图。没有模拟器/真机、实际USB驱动或外部SAF provider验收。f2ce541固件USB回调/stack/SRAM门禁也不因客户端测试而通过。

## 环境与许可

SDK仍仅cmdline-tools23.0、android-36 r2、build-tools35.0.0；Gradle8.13、现有JDK21。官方安装包指纹和关键JAR恢复校验通过，复用安装，未增加Studio/NDK/模拟器/其他SDK组件。SDK本体 **430620815字节**，整个工程和缓存采样 **1923679536字节（1.79GiB）**。仅删除本任务已验证且安装完成的命令行工具ZIP，未清理其他任务。

`android-sdk-license`，2019-01-16，来源https://dl.google.com/android/repository/repository2-3.xml；接受时间2026-10-13T05:06:19.522497Z，详情见[接受记录](evidence/sdk-license-acceptance.json)。之前的许可等待和两次断连是历史状态，已解决。

首次Android CLI默认统计提示不能证明上传或未上传，实际上传未知；后续明确--no-metrics。没有为调查此事增加上传或修改全局隐私设置。

## 后续边界

当前保持仿真/回放可测。真机安装、USB打开/CDC-UART互操作、真实SAF目录持久授权、后台/系统杀进程恢复和运行时视觉验收需后续明确授权。设备DELETE和跨连接resume继续禁用；本地已验证copy/cut另算，原始数据和卸载风险提示保留。
