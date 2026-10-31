# Final actual-run parameter adoption, 2026-11-01

This acceptance uses the final **Underline -> TreeDiagram 6DoF -> SCG** software
workflow, plus the final native PID/LQR examples. It supplements v1's mathematical
fixtures; it does not replace or relabel v1's ARM results and unresolved stack gates.
No application/firmware source was changed during this acceptance.

The exact final input bundles and run matrix are retained under
`matched-runtime/inputs`. The Underline motor dataset is the declared synthetic
bench fixture exported by the real Underline service, not a hardware firing.
The retained design preserves the source hashes, unknown calibration qualification
and `source_verified_independently=false`; none is promoted to real sensor proof.

The final Underline-derived simulation has model digest
`6ff555987dc2625712e87fc9077b8f94583b17926b98400b4b4fb60124df1ca6` and run ID
`c7122141-13be-4860-b3f8-b7780dc81754`. Its recorded 18-second trajectory reached
382.98257215989327 m, with 200.00000000000003 Ns impulse; it had not landed when
that run ended. These values describe this reference simulation only.

## Results

`validate_actual_runs.py` exited **0** using the final simulation environment:

```powershell
D:/python_software/TreeDiagram/.venv/Scripts/python.exe docs/evidence/treediagram_algorithms_20261101/v2/validate_actual_runs.py
```

It creates new output directories once; rerunning requires a new named evidence
revision rather than overwriting prior evidence.

| Actual final run bundle | Parameters checked | Generated C control output | Same-identity TreeDiagram C output |
| --- | ---: | ---: | ---: |
| Underline motor + PID | 49 | 0.015029999427497387 | 0.015029999427497387 |
| Native PID | 49 | 0.015029999427497387 | 0.015029999427497387 |
| Native LQR | 45 | -0.049142077565193176 | -0.049142077565193176 |

For each bundle, the script actually:

1. Validated the strict bundle and its link to the final matrix model digest.
2. Called SCG Preview/Apply, confirmed the original project remained unchanged,
   and explicitly attached the research mathematical core through its parameter owner.
3. Saved and reopened the adopted project, then ran normal F407 target generation.
4. Verified the complete generated `.ssdecoder` using `LogDecoderPackage_Verify`.
5. Compared every supplied scalar's owner, source manifest, unit, representation,
   target precision, decoded value and compiler-evaluated generated C macro value.
6. Compiled the actual generated `Control*ProjectConfigGet` accessor and owning
   control C source with GCC `-O2 -Wall -Wextra -Werror -fanalyzer`, then executed it.
7. Compared every returned control config field and the real control-step output
   with the exact-identity TreeDiagram C controller. LQR also re-solved its stored
   A/B/Q/R model and checked that its final float32 K matched the exported K.

The PID probe is the first `.01 rad` error step at the exported sample period;
the LQR probe uses state error `[.01, .02]`. PID `kp=1.5` differs from the plugin's
default `2`; v1 independently exercised `kp=3.25`. Each real generated config
accessor consumes the adopted value. Printing the other generated macros proves
their exact compiled parameter values; it does **not** claim that this host probe
executes every full navigation backend path.

`*-preview.json`, `*-project.json` and `*-values.json` retain the before/after,
reopened candidate and per-parameter comparisons. Target float32 conversion is
explicit, including retired saved values such as raw `1.2`; retired parameters
are not represented as active algorithm behavior. `outcomes.json` preserves each
run ID, bundle/decoder hashes and generation-profile identity. `commands.json`
and the logs retain exact compiler commands, durations and exit codes.

## Identity rejection retained

The initial default-interpreter attempt exited **1** at the implementation
identity assertion. Its NumPy was 2.4.0, while the final simulation used 2.4.1.
The guard was not weakened. `initial-rejection.json`, `validation.log`, the exact
initial script, initial project/preview and `initial-inventory.json` retain that
attempt. The retry used a separate `.work/.../control-core-v2-matched-runtime`
directory and the exact final interpreter; no rejected output was overwritten.

The successful identity is
`6a72f60b5b9bf41b16632d8f0bb5a7e9e4028106ffe8b8c2421138fd097bf824`, with SDK
source commit `4f701b4a7822302dc0f4ac858549f7cc7fa4ba0e`. The recorded native build
metadata preserves Python/NumPy/SciPy versions, compiler command and wrapper
hashes. Source identity remains fixed despite later documentation-only commits.

## Scope and remaining limits

This v2 acceptance deliberately did not rerun the complete ARM/architecture/
Power10/analyzer/artifact/stack matrix. v1 retains its distinct input configuration
and actual results: both stack reports failed and critical-contract review was
NOT PROVEN. Those outcomes cannot be counted as passes for these new parameters.

The control mathematical interface is generated and executable on the host.
There is still no target mission dispatcher or electrical actuator driver;
all bundles and outcomes retain `deployment_ready=false`. Default target linking
may collect unused control sections. No physical MCU or flight was tested.
All generated validation files belong to the recorded task directories, and
their content hashes and ownership are retained in the inventories.
