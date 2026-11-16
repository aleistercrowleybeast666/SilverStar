# 最终 F407 工程保护归档与本轮重复构建清单

两份实际完整生成工程已保存到 Git 忽略的 `dist/pf1117-evidence/` 独立目录。每份均包含 Release/Debug 的 ELF、BIN、MAP、对象、`.su`、完整生成源码、导入副本、工程模型、decoder、Make/IDE 工程、当时的证明工具及输入。没有复制外部工具链或 SDK，没有重新生成、同步新 M3 helper 或改写旧编译时代。

| 保护归档子目录 | 文件数 | ZIP 字节数 | ZIP SHA-256 |
|---|---:|---:|---|
| `f407-default-e-20261117` | 2,283 | 49,478,485 | `1f133705a4a3877b9093911a8190dd25248246e9c2f57518842a1c0ee0316acf` |
| `f407-e19-b-20261117` | 1,843 | 45,145,077 | `f936e157bf51a137320099e8b407ed945bfbbb621dfeecc24bcf2ff08df46d7b` |

每个子目录的 `Flight_Controller.zip` 旁有 `FILE_INVENTORY.json`、`ARCHIVE_RECEIPT.json`、`PRESERVE_EVIDENCE.json` 和重开说明。目标不存在检查后以独占创建方式写入。压缩后逐一读取全部成员，核对尺寸、SHA-256、目录集合及重复项，并解析归档模型；再次遍历原工程证明压缩期间没有变化。两配置分别与已封存实际编译收据核对：默认 E 每配置 510 个编译产物、E19 B 每配置 504 个。

主代理随后独立复核两份全部成员与 ZIP 总哈希并验收，见 [独立验收收据](../delivery/archive-verification.json)。这只是可完整读回的软件证据，没有执行 GUI 打开、再编译或硬件操作；硬件/飞行资格仍未证明。重开时解压到新的空目录，使用其中已有 Makefile/IDE 工程以及外部记录的工具链；不要用当前 SCG 覆盖历史工程。归档必须永久保护，不能成为临时清理目标。原始工程当前仍全部保留。

构建与证明的来源是 [原合同报告](../contracts/README_ZH.md) 中逐构型的正常生成和实际编译收据；归档操作时的仓库 HEAD `d52854c4a7b12c79dbb06cf967006e599103d24e` 不是将已有 dirty 源重新归因到该提交。两 ZIP 中 `Tools/stack_runtime.py` 均保留抽取 M3 helper 之前的实际字节，SHA 为 `eb9d7a9d51c2855dd0b256a3f76908aea75de8656eb743ec8a6be98eed7497dd`。默认 E 原始软件病例索引和 E19 B 原始索引各自保留，未为追求相同而刷新。

## 仅清单，不执行删除

[repeated-build-summary.json](repeated-build-summary.json) 列出本代理当前任务 7 个 ARM 构建子树，共 9,718 文件、904,164,673 字节；[build-inventories](build-inventories/) 逐文件记录绝对路径、相对路径、字节数、SHA、owner、对应正式命令和输入稳定收据。

| 构建时代 | 文件数 | 总字节 | 与相应保护归档同相对路径、同 SHA | 不同或归档未含 |
|---|---:|---:|---:|---:|
| 默认 A | 1,538 | 133,425,522 | 1,515 | 23 |
| 默认 B | 1,028 | 119,751,111 | 1,010 | 18 |
| 默认 C | 1,538 | 133,425,578 | 1,524 | 14 |
| 默认 D | 1,538 | 133,425,578 | 1,536 | 2 |
| 默认 E（原始最终工程） | 1,540 | 133,974,690 | 1,540 | 0 |
| E19 A | 1,520 | 131,662,196 | 1,012 | 508 |
| E19 B（原始最终工程） | 1,016 | 118,499,998 | 1,016 | 0 |

这些数字不是可整目录删除的许可。独特的旧时代、分析器、报告或新增输出不得被重复文件计数掩盖；其 565 个不同/未归档文件分别保留在清单中。这里只列本代理拥有的 `build/FCCG/SilverStar_F407` 子树，排除所有 Ground、root 的最终 `build/FCCG/Host`、其他代理、旧任务、整个工程根、源 fixture、原始输入、decoder、源码、正式日志和保护归档。没有删除、移动、暂存或提交任何文件。若根代理之后统一清理，仍需逐路径核对当时字节和保护范围，不能把该清单解释为永久授权。

在主代理独立验收归档后，按其限定的重复编译物规则另写 [cleanup-eligibility-summary.json](cleanup-eligibility-summary.json)：重新核对这 7 个当前构建子树与原清单字节完全一致，只将与已验收 ZIP 同相对路径、尺寸、SHA 的 `.o/.su/.d/.s/.elf/.bin/.hex/.map` 编译产物标为 `eligible_duplicate`，共 **9,145 文件、831,475,551 字节**。另 **565 文件、71,575,085 字节**为 `preserved_unique`，**8 文件、1,114,037 字节**为同值但仍保留的 JSON/报告。逐项资格和归档身份在 [cleanup-eligibility](cleanup-eligibility/)；只有主代理后续重新校验后才能执行，当前仍没有删除任何内容，也不授权删除整个目录。前一清单中的“验收前保留”描述为当时真实状态，本补充保留其历史而不改写。

## 可重复工具与执行结果

- [archive_projects.py](archive_projects.py)：完整归档、逐成员读回、原工程前后不变验证；本次退出 0。重复运行会明确拒绝已存在的归档或收据，不会覆盖证据。
- [inventory_repeated_builds.py](inventory_repeated_builds.py)：仅本次 7 个 ARM 子树清单；本次退出 0。目标清单目录已存在时拒绝覆盖。
- [classify_cleanup_duplicates.py](classify_cleanup_duplicates.py)：读取独立验收、核对当前文件，再分类上述有限重复编译物；本次退出 0，目标资格目录已存在时拒绝覆盖。
- 三个正式 Python 工具 Ruff 检查通过，Python 3.14.0。命令、脚本哈希、时代核对和摘要见 [EXECUTION_RECEIPT.json](EXECUTION_RECEIPT.json)。这些工具不是新固件测试，未将归档成功拼成新的 ARM/Host/硬件验收。

正式小证据由 `EVIDENCE_SHA256.json` 封存；ZIP 产品与完整 ZIP 内文件清单保留在保护的 `dist` 目录，不纳入 Git。执行时生成的 `__pycache__` 不属于正式证据。
