# F103 epoch compiler-input regressions

These two small JSON fixtures replace a dependency on the disposable
`.work/sf6_epoch_v3/ret6` directory. They contain ten exact C/header inputs and
the actual GCC `.d` output for each target. Existing checker registrations accept
them without any checker/policy modification. The original changed-source,
changed-header and unknown-dependency rejection assertions remain, now for both
STM32F103RET6 and STM32F103RFT6. Positive proof records must match exactly.

`inputs_ret6.json` restores the original RET6 scenario. Its saved project comes
from `SF6_feature_tiers_compile/feature_tiers_compile_checkpoint.zip`, entry
`generated/ret6/SilverStar.ssproject`. Its Flight header is reproduced using the
normal renderer from commit `7896c1d09a7f9138c41cdac35beef38347d94b78`. The entire
renderer blob's SHA-256 is checked before executing that first-party source.
The resulting header hash was already registered; no generated text is edited
to find an admitted hash.

`inputs.json` adds the preserved RFT6 scenario from the same archive's
`generated/rft6` project and published normal-generation Flight header. Other
required inputs come from the current owning payloads and production renderer.
The reproduction compiles each unit with its actual source graph, target forced
includes, Cortex-M3 soft-float flags, strict warnings, `.d` and `.su` emission.
Only these files are materialized; no HAL/SDK tree or full project is copied.

Reproduce into **new task-owned directories** from the repository root:

```powershell
python apps/SCG/tools/validation/mpu_epoch_binding_fixture.py --target SilverStar_F103RE --output .work/<new-task>/ret6
python apps/SCG/tools/validation/mpu_epoch_binding_fixture.py --target SilverStar_F103RF --output .work/<new-task>/rft6
```

The tests also run this reproduction and compare every captured input,
dependency rule and proof. It requires the existing ARM GCC and pinned Git blob;
it does not install or download anything. Each input retains a SHA-256 and an
owning source/archive reference.

The current freshly rendered Flight headers remain **unreviewed and rejected**;
the tests explicitly preserve that rejection. Actual compilation and comparison
show identical preprocessed epoch-unit tokens between each historical header
and its current counterpart. This is a narrow regression result, not admission
of a new configuration or a whole-program proof. No F103 firmware was linked,
flashed, or given a complete task/MSP/ISR stack acceptance by this fixture work.
