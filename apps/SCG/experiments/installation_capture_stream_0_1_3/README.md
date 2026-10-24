# Installation capture stream resource experiment

Owner: `installation_stream_resource_experiment_20261019_v3`.

This is an isolated ABI, encoder and finite queue model. It does not implement a live MCU provider, touch serial ports, or alter the flashed candidate. **Never flash `layout.elf`: it has no target startup and uses only an isolated free-CCM window.**

Read the [bounded design review](../../../../docs/internal/INSTALLATION_CAPTURE_STREAMING_EVALUATION_20261019.md) before interpreting results. A 1960-byte allocation fitting the window does not establish whole-firmware resource, concurrency, stack, source-time or calibration-quality acceptance.

From the repository root, with ARM GCC and host GCC on PATH:

```powershell
python apps/SCG/experiments/installation_capture_stream_0_1_3/run_experiment.py v6
```

Use a fresh `v<number>` suffix; existing directories are deliberately rejected. The script reads the protected candidate and the preceding resource-gate audit, saves exact source bytes, commands, complete outputs and hashes under `.work/dev013_installation_stream_20261019_<version>`, and checks candidate hashes again. It never opens a device. No cleanup is performed or authorized.

Files:

- `layout_probe.c`: static state reservations, pure bounded event encoder and host-only boundary/golden checks. The 154-byte golden input is a byte-pattern fixture, not a valid sensor record.
- `experiment.ld`: maps only the proposed new state into the observed 2632-byte free CCM window; asserts a 2048-byte feature cap and zero new `.data`/`.bss`.
- `run_experiment.py`: strict ARM/host builds, real ARM `-fanalyzer`, isolated ARM link, negative 6208-byte link case, seven finite stream checks and existing Python codec compatibility checks.
- `offline_proof.py` / `test_offline_proof.py`: fixed native sequence selection, a finite session gate, all ordered entrant pairs and cleanup acknowledgement orders, and cancellation accounting that retains unknown execution terms. These are unregistered reference models.

Retained attempts: v1 failed the host newline golden; v2 passed its original checks but failed subsequent error-reply compatibility review; v3 includes both corrections and passed its recorded scope. Do not stitch those runs into a full firmware suite. The historical v3 [results](../../../../.work/dev013_installation_stream_20261019_v3/results.json) and [retained inventory](../../../../.work/dev013_installation_stream_20261019_v3/retained_inventory.json) state remaining exclusions.

The follow-up [offline proof record](../../../../docs/internal/INSTALLATION_CAPTURE_OFFLINE_PROOF_20261019.md) records the newer v5 ARM result and 316-test software run. It preserves the same C/linker bytes and 1960-byte layout. No complete C INFO encoder, target provider or production owner has been added; full firmware stack/WCET and the 500 ms cancellation goal remain NOT PROVEN.
