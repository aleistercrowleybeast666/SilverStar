# Pure Java core evidence

Executed on 2026-10-13 with Microsoft OpenJDK 21.0.12, compiling `--release 17 -Xlint:all -Werror`. No Android SDK, Gradle, hardware, network, or third-party Java dependency was used.

Commands from the project root:

```powershell
./tools/test-core.ps1
python ./tools/test-pc-compatibility.py
```

Observed result:

```text
PASS: 56 core assertions; 152 RX frames; 456 PC-compatible records; raw replay exact match.
PASS: 287 shared LOGFILE v1 assertions; direct shared golden ASCII/POLL, unknown-identity restart at zero, retained attempts, CRC/size/SHA-256, no device deletion API.
PASS: frozen v0.1.2 Python decoded 152 Java GSP/AIR frames field-for-field; PC JSONL reader full/raw-only both yielded 31 flight samples and simulated=True. GUI/plotting imports stubbed; no rendering or hardware validation.
```

The first compile attempt used an old JAVA_HOME and failed at `--release`, before compiling sources. The script now defaults to javac/java from PATH; an explicit `-JavaHome` remains supported. The subsequent JDK 21 runs passed with warnings treated as errors.

## Coverage and boundaries

- CCITT-FALSE known vector, every single frame split boundary, byte-at-a-time feeds, 100 kB noise with bounded retained storage, bad CRC and oversize-length recovery.
- Frozen M0/Profile 0 lengths, signed SX metrics, absent NRF metrics, unknown radio flags/backend rejection, unknown sensor retention, navigation session and sensor index checks, zero quaternion invalidity.
- CAPABILITY/ACK never produce READY. Unknown profile, explicit reset, BOOT, flight telemetry, stale status, inconsistent calibration and cached confirmation revoke readiness. All command-policy outcomes deny real transmission in this release.
- A complete simulation passes through the same GSP parser and AIR decoder. Raw RX GSP replay processes each frame once and ignores TX and parsed duplicate records. Corrupt replay frames are rejected. This core performs no transport I/O.
- `build/core-tests/simulation-session.jsonl` is generated afresh, includes a simulated SESSION marker, and is checked by frozen Python GSP/AIR parsing and the actual PC `_read_jsonl` / `_extract_flight_data` methods. Only optional GUI/plotting/preferences imports are stubbed. Neither PC visual export nor UI execution is claimed.
- The TF runtime standard is now the byte-preserved `reference/integration-f2ce541/log_file_service_v1.json`, from integration commit `f2ce541382589cb606e1f5b21f6fd982357eaa54`; `SOURCE.json` records provenance and SHA-256 `4695f0cb403e250c0c00e3cceebc4a7c85cd41d5c98530f92e7aa298521a4e97`. This tightens runtime policy without changing the wire golden. The earlier `reference/shared-0.1.3` cb944b7 snapshot is retained unchanged, and its export schema remains the export reference. Tests read the integration JSON directly, check its read-only CAPS and offset-zero restart semantics, and compare the golden response with the earlier snapshot. They drive both isolated READ and complete CAPS/LIST/META/READ-to-local-publication through scripted ASCII transport.
- LOGFILE v1 verifies 191-byte request / 511-byte response bounds, one outstanding asynchronous operation, matching operation/request ID/file ID/token/offset, 64-byte maximum chunks, CRC32 ISO-HDLC and final whole-file CRC/size. Unsupported/old firmware is refused. Timeout/cancel/protocol error invalidates local CAPS/META state. Every download call negotiates CAPS and obtains META anew.
- `device_id` and `boot_id` remain `unknown`. Every download attempt creates a fresh unique local `.part` path and starts READ at offset zero after new CAPS/META; even a matching token, CRC, length, prefix or complete byte sequence does not permit reuse/continuation. Existing partial and completed files are preserved byte-for-byte and never selected for append or cache reuse. `Result.resumed()` is always false under this policy. Local SHA-256 follows whole-file CRC/size verification before atomic publication. SSLOG 0.0 and required decoder package 1.2 remain distinct; no decoder identity or Descriptor is fabricated.
- Integration CAPS and the mock default advertise `delete_supported=0`. There is no `resume_supported` wire field: `Capabilities.resumeAllowed()` and `resumeUnavailableReason()` describe local policy only. A test-only mock advertising delete support cannot create a deletion API or enable resume. There is no device-delete API or emitted DELETE request. The synthetic bytes are not a valid flight recording. Abstract/mock maintenance transport proves client behavior only; USB/firmware/device interoperability remains untested.
- Android minSdk compatibility, actual APK compilation, device installation, USB serial behavior and flight/hardware correctness are not established by these tests.

TF interface: `TfLogClient.downloadAll(Source, Path)` still returns `List<Result>` and existing `MockTfSource(byte[])` callers remain valid. `Source` provides `caps()`, `list(cursor)`, `meta(fileId)`, `read(fileId, token, offset)` and `cancel()`. `MaintenanceTfSource(LineTransport)` implements the shared ASCII protocol; `LineTransport.exchange(request, timeoutMillis)` must return one complete CRLF line and obey the timeout. Its owner must call `MaintenanceTfSource.transportReset()` on disconnect/reconnect/reboot; the next READ is blocked until fresh CAPS and META. `Result.entry()` is actual service Metadata, with `localFile()`, `resumed()`, `downloadedBytes()` and `localSha256()`. There is no generation, device identity or decoder fingerprint field invented by the client.

A failure after verified data publication but before sidecar publication leaves that artifact preserved. A later call starts an independent full download rather than recovering or modifying the earlier artifact. Sidecar metadata comes only from current protocol data and the local hash. Keep each target directory under one worker/client owner. No radio/AIR/GSP bulk binding is implemented.
