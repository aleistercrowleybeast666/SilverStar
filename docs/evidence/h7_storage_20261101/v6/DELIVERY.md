# H743 storage software validation — final v6

The blocking CubeMX SD path is replaced by a SilverStar-owned, bounded SDMMC1
DMA adapter for the exact reviewed H743 input. Imported CubeMX files remain
unchanged. This final evidence is from source commit
`09c057a67acfc10e3ff387a4a8821c8ee0e83b0c` (owning driver: `267e7ad4`; strict
coverage: `362a4e4d`; fail-closed coverage identities: `09c057a6`). SilverStar
source/evidence commits are local; no SilverStar push was performed.

Final output: `.work/0.1.3-treediagram-20261101/h7-storage-v6/final/Flight_Controller`.
Configuration: the reviewed STM32H743ZI custom CubeMX snapshot, ESKF20 x1,
SDMMC1, DCache disabled. The full model is retained as local `final-model.json`.
The owning-source snapshot digest is
`36fb7efc5117b28d831ddf4ae75eefb593bf5253e5d88bdb8c71cedf014ad6da`.
Source identities are in [compact-source-identity.json](compact-source-identity.json);
the complete local snapshot also records every SCG Python source hash.

| Final check | Actual result |
|---|---|
| ARM compilation/link | exit 0 |
| Architecture/source graph | exit 0 |
| Emitted Power10 | exit 0; **critical-contract review NOT PROVEN** |
| Actual strict ARM `-fanalyzer` compilation | exit 0 |
| Linked artifact/memory gate | exit 0 |
| Strict stack gate | **exit 2 / FAIL: unreviewed H743 build declarations or configuration** |
| Relevant Python/actual-C tests | 51 passed, 32.33 s |
| Complete emitted H743 storage runner | exit 0 |
| Complete emitted F407 storage runner | exit 0 |
| Missing owner file / missing active-owner metadata | both correctly rejected with exit 2; original metadata restored byte-for-byte |

The Host scope is the complete `storage_integrity/run_storage_integrity.py`
program, **not complete `make host-tests`**. It uses logical sensor records and
does not exercise the physical epoch path. It includes byte-offset/unaligned
FatFs integrity, seven unchanged timeout/wrong-completion/start/sync fault
expectations, logger startup and overload accounting, maintenance/failure
paths, sparse preflight logging and exact-decoder audits. Unsupported positive
record cases are explicitly listed in [summary.json](summary.json); rejection
was exercised for those records. No hardware operation was performed.

The final normal H743 logger has zero drops. Deliberate overload cases retain
their original expected-drop/accounting assertions. Reading the Host clock no
longer invents elapsed milliseconds: 1,000 repeated queries leave its tick
unchanged; explicit delay, queue/DMA wait and modeled producer steps advance
time. F407 and H743 use the same corrected model.

## Ownership and actual gate coverage

Ten retained CubeMX inputs match their original hashes. Make and both IDE
configurations compile exactly the two owning canonical C files and exclude
the two original imported C units. Local edited owning C, shadow headers or
unreviewed imported identities are rejected without overwriting them.

[coverage-proof.json](coverage-proof.json) contains each new C file's actual
Power10 source/hash line and full strict `-fanalyzer` compiler command. H743
scans 138 first-party C files. F407's 125 source/hash lines and generated Makefile
are identical to the pre-coverage baseline. The H7 selection and ownership
receipt control the two-file addition; a same-named F407/imported file does not.
No threshold, first-party exclusion or allowlist was weakened or expanded.

Make's explicit first-party entries, the active H7 owner and the exact receipt
must agree. Missing either top-level ownership metadata or the active owner
now fails before scanning. The final negative runs were performed only after
normal gates completed; the original ownership SHA-256
`910581e356be5c6168bbc76bda011fe1bd7c80194346993430f4a164dbf8eeff` was restored.

The fixed FatFs function table is retained; its operations are file-local.
The reviewed write/ioctl ABI is a compile-time requirement. Compile-time
assertions receive no runtime-density credit. The static scratch buffer is
512 bytes at `0x2401fb60`, 32-byte aligned in AXI SRAM; actual linked DMA start
and receive callback code contains the required DMB barriers. The BSP rejects
DCache, out-of-range/non-AXI transfers and foreign callback handles. Errors
quarantine the scratch and leave storage NOT READY until reset.

## Resources and unresolved proof

FLASH uses 372,132 / 2,097,152 bytes; AXI SRAM uses 218,708 / 524,288 bytes.
The DTCM MSP reservation is 8,192 bytes; its safe margin is **NOT PROVEN**.
Reserved heap and linked runtime heap symbols are both zero. ELF is 3,790,580
bytes; BIN is 372,140 bytes. Artifact hashes and actual local compiler frames
are in [linked-placement-and-local-frames.json](linked-placement-and-local-frames.json).

The strict stack gate deliberately rejects the changed H743 compilation
closure. Its reviewed manifest was not silently amended. An independent new
review of actual task paths, libraries, indirect FatFs calls, dynamic frames,
main/MSP and ISR nesting is still required. Local `.su` frames, spare RAM and
Host runtime do not prove those bounds. See [stack-report.log](stack-report.log).
Power10 is the existing F Prime-inspired project text gate; it does not prove
original Power of Ten compliance or finish whole-firmware critical-contract
review. SD electrical behavior, MCU WCET/cache interaction, power-loss recovery,
board timing and flight qualification remain untested/unproven.

## Reproduction and retained failures

[commands.json](commands.json) records the exact emitted Make invocations and
exit codes. The two `*-storage-host-command.json` files record their actual
commands and scope. [tool-versions.json](tool-versions.json) records Python
3.14.0, Host GCC 16.1.0, ARM GCC 14.3.1 and GNU Make 4.4.1. Local reproducible
generation/gate/audit scripts live beside this report; generation refuses to
overwrite an existing output, so a rerun needs a new versioned destination.

[evidence-index.json](evidence-index.json) retains original log hashes, line
numbers and excerpts/records for the blocking driver rejection, 287-drop Host
clock failure, actual-C deadline/error failures and pre-fix coverage gaps.
In particular, **v1–v4 Power10/analyzer success did not cover the two new owning
C files and is not acceptance evidence for those files**. v5 probes exposed
strict prototype/conditional-compilation problems and the missing-metadata
fail-open; the final v6 fixes have their own executed evidence. Earlier
results are preserved, never substituted for this final run.
