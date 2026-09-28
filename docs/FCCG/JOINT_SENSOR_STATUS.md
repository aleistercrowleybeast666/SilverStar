# Joint sensor status

Per-model implementation, source pins/licenses, readback/persistence boundaries
and actual evidence are maintained in
[SENSOR_LIBRARY_VALIDATION.md](SENSOR_LIBRARY_VALIDATION.md).

BMI088 raw200 remains unqualified. Separate Sync400 I2C/SPI plugins implement
Bosch synchronization and require declared wiring plus runtime IRQ pairing. All new
sensor hardware remains `HARDWARE_UNVERIFIED`. No physical testing was performed.
Repository-wide acceptance is recorded in [VALIDATION.md](VALIDATION.md).
