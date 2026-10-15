# Native USB workflow evidence — 2026-10-15

This development batch connects the experimental capability/lifecycle adapter to
SCG's saved project model, application service, explicit derived source graph,
ARM build runner and build-page controls. See the
[workflow description](../../../apps/SCG/docs/USB_NATIVE_WORKFLOW_20261015.md)
and [compatibility audit](../../../apps/SCG/docs/USB_CDC_COMPATIBILITY_20261015.md).

- [evidence.zip](evidence.zip): 5,884,598 bytes, 3,461 entries; SHA-256
  `e56970d3112424d4f5ef40e8e69f11fa302a4a706002e873c37f53f69c307061`.
- [archive.json](archive.json) records archive and 20 scoped source-file hashes.
  The archive contains a verified per-entry manifest and the exact dirty USB
  source text against base commit `cb53daf3f3a88b55b7ed1fbf1fd39678487f6f18`.
- [summary.json](summary.json) distinguishes compatibility evidence, final product
  builds, unchanged source bindings and remaining blockers. The earlier worker
  source snapshot remains tied to its own `5af1efa1` base and exact dirty bytes.

## Executed results

| Run | Result |
| --- | --- |
| Product `native_usb_workflow06` | **26 passed**, no skips; includes source/kit/graph tampering, old/new project serialization, ownership, GUI background/stale-result handling, existing-output preservation and real Windows parent/child cancellation |
| Existing targeted SCG regressions `native_usb_existing01` | **156 passed**; task-progress, feature-tier and NIS probability modules |
| UI selection `native_usb_ui01` | **4 passed, 40 deselected**; this is not a 44-test execution |
| F103 and F407 product `native_usb_*03` | Four fresh complete ARM links: normal and actual `-fanalyzer` for each target; ELF attributes, USB vector and transport symbols verified; receipts rechecked |
| Analyzer diagnostics | Two warnings in each unchanged vendor UART HAL; retained, not waived or classified as proven false positives |
| Compatibility worker `validate12` | **Aggregate exit 1**; 214 commands, Host **98 passed / 5 skipped / 1 warning**, four links and effective SDK preprocessing, failed Power of Ten gates |
| Power of Ten | **FAIL**, F103 7 reported groups and F407 10; gate unchanged, critical-contract review **NOT PROVEN** |
| Panel visual review | Chinese/English offscreen panels captured; labels/actions fit at 1000-pixel width; native input and failure/diagnostic state visible. Explicit local Windows font loading was needed in offscreen mode; no font redistributed |

Tool versions, full commands, return codes, logs, inspected native source inputs
and upstream license files are retained. Every product build includes effective
header hashes (88 F103 / 97 F407), compiler dependencies, linked library hashes,
ELF/map/vector/stack-usage files and its own receipt. Normal and analyzer ELF hashes
are listed in `summary.json`. No historical binary is relabeled as a fresh build.

The final Windows termination error-reporting change followed the four ARM03
builds; it changes neither the compiler commands nor C inputs. The exact delta
and final workflow test scope are recorded in `summary.json`. Final failure-path
testing does not imply another execution of the earlier ARM builds.

Earlier results are retained separately: missing fixture import, missing native
input causing eight skips, and sandbox credentials preventing `taskkill`.
`workflow05` is **25 passed / 1 failed**, not a successful complete run.
`cancel01` reproduces the sandbox restriction; `cancel02` passes with ordinary
local permissions; `workflow06` is the subsequent complete 26-test execution.
No separated passes are combined into an unexecuted full-suite result.

## Open items and preservation

The original F407 input lacks CDC notification TX2 allocation. Its runtime guard
rejects that configuration. Isolated CubeMX generation first failed on Java
preferences and then timed out waiting for a third-party lock. The proposed
native-owned template was **not applied**. The original input hashes are unchanged;
no corrected-F407, usable clock/IRQ, or physical lifecycle claim is made.

The task-owned CubeMX home unexpectedly extracted 632,135,209 bytes of browser
and MCU database cache. Its inventory is retained, but those cache bodies are not
duplicated in this archive. No full firmware SDK download, user-project rewrite,
hardware operation, publication or cleanup was performed. The only separate
navigation draft withdrawal in this working session is documented in its own
task and is unrelated to this USB evidence.

Gate failures, vendor diagnostics, native FIFO configuration, complete critical
contracts, call graph, full stack/ISR bounds, target WCET and hardware validation
remain unresolved. Ground admission gates are unchanged. TF log download and
deletion remain future protocol/storage work; this batch adds no file service.

Task outputs remain under `.work/dev013_usb_workflow01` and
`.work/usb013-compat-20261015`. This archive and original native source inputs are
retained evidence, never temporary-cleanup targets. No cleanup authorization is
implied by the inventory.
