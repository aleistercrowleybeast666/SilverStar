# Installation capture 0.1.3 — experimental, default off

This optional declarative component owns the installation capture C implementation,
its native-sample adapter, and the maintenance ASCII dispatcher. No preset selects
it. Developer opt-in adds `silverstar.installation.capture` to the project's base
components; it is not a navigation algorithm selection or a new GUI choice.

The generator requires the STM32F4 core, maintenance protocol, and exactly one IMU
and one MAG endpoint. Generated endpoint labels come from the selected source graph.
The unselected core uses state-free inline stubs.

The target build currently rejects `BEGIN` with `SOURCE_QUALIFICATION`. Native
delivery, boot identity, measurement-time semantics and raw-value definitions have
not been qualified. Unknown values remain explicit; the adapter never invents
synchronization or consumes a second IMU FIFO. Synthetic host fixtures use the same
C transaction path with explicitly synthetic proof. Upload, APPLY and SAVE are off.

See [software integration and remaining work](../../../../../docs/internal/INSTALLATION_CAPTURE_SOFTWARE_INTEGRATION_20261019.md)
and [installation design](../../../../../docs/internal/INSTALLATION_CALIBRATION_0_1_3_DESIGN_20261018.md).

`payload/ThirdParty/InstallationCapture` retains the pinned upstream Ryu
commit and both upstream licenses. Its provenance and local warning-safety changes
are recorded in the task evidence; it remains third-party code. A scoped Ryu
assertion bridge routes internal preconditions to `SilverStarAssert_Fail`; it
does not install a global libc assertion override or disable upstream checks.
