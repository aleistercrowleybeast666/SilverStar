# Monorepo 构建与来源

源码位于 `apps/GSHC_Android`，没有嵌套 `.git`。原项目没有 Git 历史，导入前逐文件核对
116 文件迁入清单中的 Android 100 文件；原路径/字节数/SHA-256 见 MIGRATION_SOURCE.json。
协议/reference 和历史 evidence 原文保留，不将历史测试结果当迁入后结果。

现有 SDK、Gradle、JDK 和缓存复用；本轮没有下载/安装工具或接受新许可证。
SDK/Gradle 位于 `D:/python_software/SilverStar_GSHC_Android/build/toolchain`，缓存位于
其父目录 `build`。它们不属于 Git 源码，路径可用参数或以下环境变量配置。

从仓库根运行本轮离线回归：

```powershell
$env:JAVA_HOME = 'C:/Program Files/Microsoft/jdk-21.0.12.101-hotspot'
$env:SILVERSTAR_ANDROID_TOOLCHAIN_ROOT = 'D:/python_software/SilverStar_GSHC_Android/build/toolchain'
$env:SILVERSTAR_ANDROID_CACHE_ROOT = 'D:/python_software/SilverStar_GSHC_Android/build'
$env:SILVERSTAR_ANDROID_BUILD_ROOT = "$PWD/.work/dev013_monorepo01/android-build"
$env:SILVERSTAR_ANDROID_PYTHON_DEPS = "$env:SILVERSTAR_ANDROID_CACHE_ROOT/python-deps"
./apps/GSHC_Android/tools/build-android.ps1
./apps/GSHC_Android/tools/test-core.ps1 -JavaHome $env:JAVA_HOME -BuildRoot $env:SILVERSTAR_ANDROID_BUILD_ROOT
./apps/GSHC_Android/tools/test-storage.ps1 -JavaHome $env:JAVA_HOME -BuildRoot $env:SILVERSTAR_ANDROID_BUILD_ROOT
.venv/Scripts/python.exe apps/GSHC_Android/tools/test-pc-compatibility.py
.venv/Scripts/python.exe apps/GSHC_Android/tools/test-shared-export.py
```

./apps/GSHC_Android/tools/build-android.ps1
已有缓存离线构建，禁止 SDK 自动下载，依赖不足时失败并报告。没有复制 SDK、缓存、
虚拟环境、APK 或 keystore 入 Git。debug key 只引用外部已有路径，不是发行签名。
默认本地 BuildRoot 为应用的 `build`，同样被忽略。

APK 输出在 `<BuildRoot>/app/outputs/apk/debug/app-debug.apk`。不要依赖原工程绝对源码路径。
真实 USB、设备删除/控制与跨连接续传仍关闭；Robolectric 和 fixture 测试不是手机/硬件验收。
原来源源码在验证后以可恢复方式保留，未永久删除来源目录。详见迁入报告。
