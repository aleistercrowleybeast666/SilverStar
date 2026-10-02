# Field integration 2026-10-02

Fresh paired candidate from bb2281b1bcd11334ae47944e62f7005fb55479a2. Base f0abb6 plus only RF 0826/2395 and
86efd test/docs (local cherry-picks 99f54cd, 6d6ff62, bb2281b). No new production
changes, no Baro backup/SF6/GUI extras, no hardware, main merge, push or tag.
Configuration: KF6, VectorConstraints, Coning2Sculling2, one JY901B, one NEO-M9N,
E28/SX1281, logging/storage enabled, Delay 10 seconds; existing F103C8T6 Ground.
RF frequency 2473000000, SF10, requested BW800000 (chip BW812500), CR4/5,
preamble16, explicit header and CRC. Both endpoints are generated together from
the same project. Ground must be replaced with this new role-aware candidate;
new Flight with frozen Ground50 is a preserved failed mixed pair.

The RF precondition checked fifteen prior command exits, clean upstream source,
only Host fixture/docs changes after 2395, canonical Git LF identity and eight
actual generated RF raw-byte matches. Initial canonical comparison encountered
ordinary tracked CRLF checkout conversion; normalization was used only against
the Git object, never to weaken generated-payload byte comparison.
The complete upstream RF evidence archive is retained byte-for-byte, including
failed timing/SPI and mixed-pair evidence. Prior optional START counterexamples
and exact owning functions remain under OPTIONAL_GNSS_START_20261002 with their
original source attribution; they are not relabeled as new integration results.

All fifteen new gate commands must actually exit 0 before packaging. Flight Host
includes the actual Alignment/INS/calibration/health/storage admission/Freeze/
Prepare/START integration variants; no critical readiness interface is stubbed.
It covers optional no-fix admission, explicit required GNSS and required attitude/
barometer/storage rejection, normal origin START and prohibition of late origin.
Paired RF pytest explicitly receives the new generated Flight and Ground paths
and retains source-hashes, compile records, per-scenario logs and exit files.
This includes variable owner jitter from 86efd and the SPI read/command faults.
GSHC tests execute the optional fix already in f0abb6. M0/AIR wire sources are
unchanged and NAV remains informational rather than a second START authority.

PoT textual gates still report critical-contract NOT_PROVEN. Ground has no emitted
stack-report target; its real linked memory/source-graph checks and all compiler
.su reports are retained. Ground actual task/ISR stack and radio timing remain
NOT_PROVEN. ARM nano-library syscall warnings at Ground link are preserved;
they are not new first-party compiler diagnostics and have not been suppressed.
Gate results cannot establish flight qualification or authorize a hardware burn.

Tool identities: exact shared read-only venv Python3.14.0, ARM GNU14.3.1,
UCRT64 GCC16.1.0, mingw32-make4.4.1; -j2 SHELL=cmd.exe, explicit PYTHON and
venv-first PATH. No environment installation or shared venv mutation.
Manifest contains absolute build/frozen paths and hashes. The source-and-paired-
firmware archive and archive verification manifest are independent new files;
earlier optional/RF candidates and frozen packages remain unchanged.
