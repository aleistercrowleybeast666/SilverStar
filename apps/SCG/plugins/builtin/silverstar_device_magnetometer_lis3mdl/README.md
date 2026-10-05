# LIS3MDL magnetometer

One physical LIS3MDL plugin supplies I²C and four-wire SPI variants. The current `uhp_20_hz_4g` profile configures 20 Hz, ±4 gauss, ultrahigh-performance XY/Z, temperature acquisition and block data update. The bounded startup reads all five control registers, writes only differences and verifies each write before waiting for a fresh XYZ sample. A process tick performs at most one bus transaction; reads of the output burst cannot replay an old status event.

The driver reports raw counts, physical magnetic field in µT and the chip's nominal temperature. It does not claim calibration. Register, sensitivity and interface limits come from the [ST LIS3MDL datasheet](https://www.st.com/resource/en/datasheet/lis3mdl.pdf); the [ST application note AN4602](https://www.st.com/resource/en/application_note/an4602-lis3mdl-threeaxis-digital-output-magnetometer-stmicroelectronics.pdf) gives the 25 °C temperature zero. This software path remains **HARDWARE_UNVERIFIED**.
