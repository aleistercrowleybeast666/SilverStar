# H743 SDMMC owning-adapter evidence

The final report is [v6/DELIVERY.md](v6/DELIVERY.md) and machine-readable
[v6/summary.json](v6/summary.json). All version directories are retained.
Only v6 represents the final source `09c057a67acfc10e3ff387a4a8821c8ee0e83b0c`.
The strict stack gate fails (exit 2); critical-contract review and hardware
qualification remain unproven. Do not combine earlier selected passes into a
claim that a complete `make host-tests` or whole-firmware proof was executed.

The evidence includes original blocking-driver rejection, actual-C fault
before/after results, Host clock-model correction, strict first-party coverage
and metadata-consistency failures, commands, full logs, artifact hashes and
versioned generated-output inventories. Generated firmware is test output under
`.work/0.1.3-treediagram-20261101/h7-storage-v*/`; it is not a hardware candidate
delivered to the user's imported CubeMX directory. No imported source was edited,
no hardware was operated, and no SilverStar push was made.
