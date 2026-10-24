# F407 optional magnetic resources and maintenance log export

`build.magnetometer_enabled` and `build.maintenance_log_export_enabled` are independent boolean choices in the SCG global device configuration. Full and Standard default to enabled. Compact and Minimal disable both; a saved project explicitly enabling either in these tiers is rejected. Custom choices use project format 21. Older default projects retain their existing serialization, with bounded tiers resolving to the new disabled policy.

Magnetic sampling requires a declared, supported physical-unit endpoint. Disabling magnetic resources removes MAG descriptors, capability providers, correction/storage state and the JY901 magnetic adapter from the selected source graph. Unsolicited magnetic frames no longer update the shared IMU magnetic validity, timestamps, counters or raw cache. Shared gyro/accelerometer context remains. Magnetic correction operations report NotPresent, and effective magnetic log records are disabled while saved record choices remain available for restoration. Enabling sampling does not authorize magnetic fusion/alignment against the release policy.

Maintenance TF export requires both maintenance and logging protocols. Disabling export selects a bounded unsupported implementation and removes the file-service mailbox, scratch and private read/enumeration storage adapter. It does not disable ordinary TF SSLOG recording, its queues or its storage service. TF deletion remains unsupported.

Make and EIDE select the same implementations and explicitly exclude inactive sources. The owning payload contains both implementations for provenance and first-party text checks. No new preprocessor exception, heap allocation, stack reduction or resource-budget relaxation was introduced.

For the recorded F407 configuration, actual linked on/off allocations are:

| Region | Enabled | Disabled | Reduction | Physical capacity |
|---|---:|---:|---:|---:|
| Main SRAM | 102,300 B | 102,260 B | 40 B | 131,072 B |
| CCMRAM | 63,288 B | 60,216 B | 3,072 B | 65,536 B |

The 102,400-byte main-SRAM regression budget has 100/140 bytes of headroom. This is distinct from 28,772/28,812 physical unallocated bytes. CCM has 2,248/5,320 physical unallocated bytes. Neither quantity establishes runtime MSP/ISR or task-stack margin.

The main consumers are navigation replay/state, the normal logging queues, radio driver contexts and IMU input queues. In CCM, static task stacks, estimator/replay state and shared Console diagnostics dominate. Magnetic calibration and export are smaller, mostly-CCM contributors; normal logging cannot be attributed to export alone.

Evidence is retained in `.work/dev013_gshc_accept24_resources01`: source snapshots, on/off generated projects, complete map files, per-symbol DWARF owner/region CSVs, `VARIANT_COMPARISON02.json`, GUI captures, actual ARM builds/analyzers, exact gate revisions and regressions. The final related software run recorded 174 passing tests. Interrupted and failed earlier runs remain recorded. Continued hardware evidence and user-blocker comparison belong to `.work/dev013_gshc_accept25_finish01`; software checks alone are not hardware qualification.
