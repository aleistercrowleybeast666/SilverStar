# Experimental USB CDC transport evidence, 2026-10-13

This records the 0.1.3 source-checkout developer kit described in
[the design and compatibility matrix](../../USB_CDC_TRANSPORT_20261013.md).
It is software evidence for an additive, protocol-independent transport.
**ABI_ONLY_NOT_HOOKED_TO_NATIVE_CALLBACKS** applies to both representative
native links. Existing private Ground callbacks still own USB in those images.
The new transport was executed only in the recorded Host fault-injection tests.
Physical USB operation and deployment acceptance remain **NOT PROVEN**.

## Read the records

- [index.json](index.json) binds current source, run snapshots, native inputs,
  actual retained libraries, generated files, linked images, function stack
  frames and every archived record by SHA-256.
- [audit-records.zip](audit-records.zip) retains 177 compact records: complete
  top-level logs and commands, source snapshots, failure history, native backend
  command logs/receipts, configuration, emitted gate, license/version files and
  the collection script. It contains no compiled firmware or SDK tree.
- [SHA256SUMS.json](SHA256SUMS.json) binds these deliverables and the six new
  implementation/design/test/validation files before root integration.

Full source snapshots, maps, binaries and all `.su` files remain under
`D:/python_software/SilverStar/.work/usb013`. The two final native outputs are
`final03/native/o_8f623d67/b` (F103C8T6) and
`final03/native/o_272613ae/b` (F407VET6). All 947 and 1,069 inventoried files,
respectively, were rehashed at collection. They are retained evidence, not
authorized cleanup targets. No old `.work` directory was cleaned.

## Separate executed scopes

| Run | Observed result and scope |
| --- | --- |
| `baseline01` | Frozen `c31c13c` implementation compiled; the new 512-byte capacity requirement returned 511 bytes and one dropped byte, expected exit 1. This reproduces a feature gap, not a violation of the old documented drop policy. |
| `version01`, `version02` | Initial version check failed on pre-existing stale plugin expectations. After aligning their independent existing versions, 1 passed. No plugin manifest was changed by this stage. |
| `tests01` | 13 passed, 2 failed: capability heuristic incorrectly matched CMSIS cache declarations. |
| `tests02` | 13 passed, 2 failed: redirected Documents ancestor was rejected. |
| `tests03` | 15 passed after the above inspection fixes. |
| `final01` | 17 Host passed; 2 native tests failed while capturing a git diff using default GBK decoding. No successful native compilation claimed for this run. |
| `final02` | 17 Host and 2 native tests passed; recorded ARM/analyzer/link/gates passed. This is the earlier revision, retained as history. |
| `final03` | 20 Host passed; 2 real native backend tests passed, 26 deselected. Both generated adapters compiled and linked with real native CMSIS/HAL/USB sources, strict warnings and real ARM `-fanalyzer`. All recorded gates exited 0. |
| `export04` | 21 Host passed after bounded-read and exclusive output-publication changes; no target build requested. Its current renderer SHA and every emitted target file match `final03`. |

The pytest runs record one existing `cache_dir` configuration warning. The Python
installation also prints its recorded location warning. These are not suppressed.
`final01` was fixed by explicit `PYTHONUTF8=1` and `PYTHONIOENCODING=utf8`, not by
discarding undecodable bytes. `final03` and `export04` are distinct executed runs;
they must not be presented as one unexecuted full repository test run.

Native backend receipts retain 339 (F103) and 387 (F407) actual commands, exact
dirty snapshots, toolchain version, parsed configuration and linked source graph.
The additional ABI graph and `final03/commands.json` record each new compile,
analysis compile, link, ARM attribute, symbol, independent IRQ-vector and size
check. The original native ELF is separate from the new `usb-transport-abi.elf`.
Both the normal and analysis links retain all eight public transport operations.
The inspected archives contribute 13 retained members per ABI image; their
paths and archive hashes are recorded, without treating discarded members as
retained code. Original native input licenses remain authoritative.

The Power of Ten command was extracted from each fresh emitted Makefile and
executed unchanged:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File Tools/check_power_of_ten.ps1 -TargetKind Ground
```

Its source coverage includes `Generated/UsbTransport/Src`. Both gates returned
zero, while explicitly reporting `POWER10_CONTRACT_REVIEW|NOT_PROVEN`. The rule 5
recommendations are nonblocking under the recorded F Prime-inspired project
adaptation; this is neither original Power of Ten compliance nor certification.

## Contract checks and remaining limits

Host tests cover full-capacity RX and wraparound, all-or-none packet publication,
backpressure/rearm ownership, caller-independent TX storage, TX BUSY and trailing
ZLP lifetime, ambiguous post-call submit/rearm failures, offline sessions,
confirmed retirement before reconnect, session exhaustion and corrupt-state
fail-stop. Both ST class handle ABIs distinguish harmless precheck BUSY from
ambiguous post-call BUSY. Export tests cover rejection reasons, native input
preservation, changed-input rejection, concurrently created output preservation,
and actual CMake compile/link for both BUNDLED and EXISTING assertion ownership.
Host-only terminal-trap interception never enters target firmware.

The target core uses bounded copy loops, static buffers, one interrupt-masked
state owner and fixed port calls. The new function frame files report static
frames, but do not prove combined task paths, library bounds, indirect calls,
main/MSP or ISR nesting. Unknown middleware LL error propagation, actual endpoint
cancellation, interrupt latency, USB clocks, hardware enumeration/reconnect and
full manual critical-contract acceptance remain NOT PROVEN. No safety exception,
gate threshold or existing admission rule was broadened. No serial/DAP action,
flashing, actuator access, push, tag or release occurred.

## Reproduce into a new output directory

Commands and their exact absolute arguments are retained in each run's
`commands.json`; these abbreviated entry points require this source checkout,
the recorded local tools and the complete native input/configuration paths:

```text
python -B apps/SCG/tools/validation/usb_transport_baseline.py --output <new-baseline-directory>
python -B apps/SCG/tools/validation/usb_transport_validate.py --output <new-directory> --reference <native-reference-root> --config <candidate-config.ssproject>
python -B apps/SCG/tools/validation/usb_transport_validate.py --output <another-new-directory> --reference <native-reference-root> --config <candidate-config.ssproject> --host-only
```

Use `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUTF8=1`,
`PYTHONIOENCODING=utf8`, and the recorded GCC/ARM toolchain on PATH. The validator
sets the child environment explicitly and never executes an imported Makefile.
Its fresh generated outputs are separate from the user's final candidate.
