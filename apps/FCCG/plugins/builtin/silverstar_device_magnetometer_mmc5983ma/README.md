# MMC5983MA magnetometer

One physical MMC5983MA plugin supplies I²C and four-wire SPI variants. The `oneshot_20_hz_8g` profile uses an explicit SET and magnetic conversion at a bounded 20 Hz cadence. Startup checks the 0x30 product ID, reads control registers 1 and 2, writes only differences, and verifies readback. Each process tick performs at most one bounded bus transaction. A fresh magnetic measurement gates READY; its 18-bit unsigned axes are centered at 131072 counts and converted with 16384 counts per gauss.

After each magnetic sample the driver requests a temperature conversion. A temperature timeout publishes the valid magnetic sample without a temperature-valid flag. No calibration is claimed. Register layout, sensitivity, conversion timing and interface limits come from the [MEMSIC MMC5983MA datasheet](https://www.memsic.com/Public/Uploads/uploadfile/files/20220119/MMC5983MADatasheetRevA.pdf). This software path remains **HARDWARE_UNVERIFIED**.
