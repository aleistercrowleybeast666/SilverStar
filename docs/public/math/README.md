# 惯导与三套融合算法：实现数学文档

直接阅读[15页PDF](navigation-models.pdf)，或编辑[main.tex](main.tex)。`sections/` 下九份TeX是维护源，不是只有ZIP的不可读附件。覆盖 Pure INS、SF6 revision 2、KF6 process-model revision 2 和 ESKF15，并解释坐标/符号、外部校准与初对准、延迟/质量/健康边界以及固件和FLP差异。

产品版本为0.1.2。数学源码审阅基线为 `234caa5f6d8e704739edb897078666274fca0673`；89份C/header/Python/JSON源码SHA256在集成前再次确认未变。PDF和10份TeX保持审阅/编译/逐页视觉检查后的原始字节；本次仅集成与核对，没有重新执行固件验收。最终分发commit及文件hash见根 RELEASE_MANIFEST.json。

## 文件结构

- `main.tex`：主文档入口与统一符号。
- `sections/scope.tex`、`symbols.tex`：范围、坐标、符号与单位。
- `sections/mechanization.tex`：二子样圆锥/划桨与Pure INS。
- `sections/sf6.tex`：六轴固定增益与当前状态语义。
- `sections/kf6.tex`：六状态、原始T过程噪声、分组更新与有限历史回放。
- `sections/eskf15.tex`：右误差、残余bias、线性化、杆臂、注入和完整协方差reset。
- `sections/preparation.tex`、`diagnostics.tex`、`evidence.tex`：校准/对准、质量窗口/健康、实现来源与证据限制。

## 维护和编译

保留主文件与sections相对结构；在本目录用已有、依赖齐备的pdfLaTeX编译两次，使目录和交叉引用收敛。MiKTeX可用下例禁止自动安装包；其他TeX发行版参数可能不同。本分发不附TeX引擎或包，也不自动安装它们。

```powershell
New-Item -ItemType Directory -Force build | Out-Null
pdflatex --disable-installer -interaction=nonstopmode -halt-on-error -file-line-error -output-directory=build main.tex
pdflatex --disable-installer -interaction=nonstopmode -halt-on-error -file-line-error -output-directory=build main.tex
```

现有复核已完成结构、编译与15页视觉检查；PDF SHA256为 `53861059c54d9e0d2d4ae11b25bd72df921b2ebda3521b1d1a823648646093a8`。内部命令日志、审查报告及渲染缓存不随公共目录发布。

本文是实际实现说明，不是理想公式替代代码，也不证明导航真值、硬件/飞行适用性、栈或WCET。旧数学revision/记录保持原身份；USB BLOCKED、PoT critical-contract NOT PROVEN及既有失败/skip不会因公式文档编译而消除。返回[算法说明](../algorithms/NAVIGATION_IMPLEMENTATION.md)或[公共总入口](../README.md)。
