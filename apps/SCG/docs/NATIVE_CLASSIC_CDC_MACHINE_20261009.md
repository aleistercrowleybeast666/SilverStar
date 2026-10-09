The CPU/IRQ increment addresses the two P2 findings in the independent review
of b0df77f. It retains that candidate archive and every historical result. It
does not enable normal firmware generation or establish a complete runtime.

Native admission now checks effective startup CPU/architecture/FPU directives.
The real compilation validator checks GCC-produced assembly, every C/assembly
object's ARM attributes and both linked ELF files against independent device
facts. An actual M4 `qadd` object assembled under M3 command-line flags is rejected
by the attribute check; command-line flags alone are insufficient evidence.

IRQ numbers come from a caller-reviewed external device header, recorded with
its source and SHA-256. The imported CMSIS header must have the same bytes. Both
startup declarations and actual binary vectors must bind each required strong
handler to independent IRQn+16. Swapping handler names throughout startup no
longer makes its wrong vector placement self-consistent and acceptable. The
caller must establish trust in these facts: a digest is identification, not
authentication. The external headers used here are the installed ST F1 1.8.7
and F4 1.28.3 SDK copies under D:/Tools/Embedded/STM32/Repository, outside input.

The four native mutation cases failed before correction and passed afterwards.
The final scoped admission/machine run had 62 passes in 147.99 seconds, no skips,
and the existing pytest cache_dir configuration warning. It includes a real
ARM M4-override object and binary IRQ-slot mutation, not MCU execution.

Fresh F103 and F407 normal/analyzer builds completed every recorded compiler,
closure, linker, architecture-attribute and independent vector check. Their
strict validation results remain FAIL/exit 1: each original HAL UART source
reports two analyzer null-pointer warnings. No diagnostic was hidden or waived.
F103 records 225 commands and 365 artifact hashes; F407 records 279 commands and
455 artifact hashes. Every artifact hash was rechecked before evidence copying.

Complete pre/post logs, commands, compiler version, source baseline plus dirty
snapshot/full new module sources, independent facts, inputs and artifact hashes
are in [the verification manifest](evidence/native_classic_cdc_machine_20261009/verification.json).
The recorded source baseline is b0df77f with the auditable machine increment.
The separate native_clock experiment was not linked in these builds and is not
included in this increment's acceptance claims. No generated C payload or
Power-of-Ten checker changed in this Python-only increment; previous emitted
gate runs retain their recorded revisions and scope, not a newly executed pass.

NOT PROVEN remains explicit for the Ground runtime adapter, EP0/async CDC
lifecycle, SPI/time/GPIO behavior, semantic critical-contract review, whole
program stack/WCET and hardware. No user project, daily checkout, GUI, FINAL
candidate, board, flash operation or remote was changed by this increment.
