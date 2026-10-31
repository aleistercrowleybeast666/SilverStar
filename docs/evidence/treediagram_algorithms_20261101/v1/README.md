# TreeDiagram control-core validation, 2026-11-01

This is a **partial acceptance record**, not whole-firmware or hardware qualification.
Two fresh F407 projects exercised the normal SCG source graph with the explicit
PID/LQR mathematical build interface. Neither controller is dispatched by the
default MCU mission/actuator task; unused controller sections can be linker-collected.

The owning sources were dirty when this run began. `source-snapshot.json` records
2,035 source file hashes and baseline HEAD. All 2,035 files were subsequently
committed unchanged in `4f701b4a7822302dc0f4ac858549f7cc7fa4ba0e`; the final
comparison found no changed or untracked source paths. `inputs.json` preserves the
two complete project models and frozen input bundle hashes. `inventory.json`
preserves the exact generated files, binaries, paths, sizes and hashes from this run.
The frozen fixture SDK/host identity predates the final TreeDiagram host adapter;
these fixtures remain compatibility inputs and are not evidence of that later
host binary. Final TreeDiagram runs use its separately recorded final SDK identity.

Command from repository root:

```powershell
python apps/SCG/tools/validation/treediagram_control_validate.py --revision v1
```

The script exited **1**, because both stack reports failed. All commands, tool
versions, exit codes and elapsed times are retained, without combining results
from other output trees. GCC 14.3 ARM and the recorded MinGW GCC were used.

| Check | PID | LQR |
| --- | --- | --- |
| Generated accessor + actual C core: strict Host GCC `-fanalyzer` | 0 | 0 |
| Actual Host consumer execution | 0 | 0 |
| Normal ARM `all`, compile/link | 0 | 0 |
| Generated `architecture-check` | 0 | 0 |
| Generated `power10-check` | 0 | 0 |
| Generated `static-analysis`, actual ARM `-fanalyzer` compile/link | 0 | 0 |
| Generated `artifact-check` | 0 | 0 |
| Generated `stack-report` | **2** | **2** |

Power of Ten text results: PID 7,127 checks / 127 first-party C files /
3,104 functions / 999 recommendations; LQR 7,119 / 127 / 3,100 / 998.
Both explicitly report `POWER10_CONTRACT_REVIEW|NOT_PROVEN` and manual
acceptance pending. These results do not establish original Power of Ten
compliance, safe MCU timing, navigation accuracy or a safe stack margin.

Both stack reports reject the existing reviewed callback dependency hash for
`Generated/Inc/project_flight_config.h`. The exception/allowlist was not widened,
and no completed stack proof is claimed. The complete tracebacks are retained.

The real normal-generated PID config consumes changed `kp=3.25` (default 2)
and produces `0.0325199999` for the recorded first step. The LQR consumer reads
float32 `k_angle=2.96664548` and produces `-0.053943418` for `[0.01, 0.02]`.
Both outputs came from executing the owning C implementation and generated
`Control*ProjectConfigGet` accessor, not Python copies of the control equation.

Additional read-only roundtrip validation, exit 0:

```powershell
python docs/evidence/treediagram_algorithms_20261101/v1/check_decoder_roundtrip.py > docs/evidence/treediagram_algorithms_20261101/v1/decoder-roundtrip.json
```

The existing full `LogDecoderPackage_Verify` checked each real generated
`.ssdecoder`. Every controller scalar and the shared INS/KF6 gravity
`9.806650161743164` agree across input bundle, generated C header and decoded
firmware semantics. This preserves the original strict scalar schema/capacities.

The final code-commit bundle regressions are logged separately in
`tuning-bundle-tests.log`, run from `apps/SCG` with:

```powershell
python -m pytest tests/test_tuning_bundle.py --basetemp=../../.work/0.1.3-treediagram-20261101/bundle-final-tests -q
```

No physical MCU, actuator, GNSS receiver or flight was exercised. The remaining
mission dispatch/electrical interfaces, full critical-contract review, callback
dependency review and complete task/MSP/ISR stack bounds remain unverified.
All `.work/0.1.3-treediagram-20261101/control-core-v1` outputs belong to this
validation; no user flight candidate or previous evidence was overwritten.
