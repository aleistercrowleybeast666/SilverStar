# BMP280

One physical BMP280 plugin provides I²C and SPI interface variants. Both use the
same bounded, one-bus-transaction-per-tick core. The I²C variant fixes SDO low
(7-bit address `0x76`); use SPI when that wiring is unavailable. The configured
forced-mode profile supplies fresh pressure and temperature at a nominal 20 Hz.
Altitude is derived in the SilverStar common barometer layer from pressure; the
driver does not claim a hardware altitude or native variance measurement.

Identification, calibration trim, filter read/diff/write/readback and first
fresh sample precede readiness. The driver uses no dynamic allocation and is
currently **HARDWARE_UNVERIFIED**. Register and compensation rules follow the
[Bosch BMP280 datasheet](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmp280-ds001.pdf).
