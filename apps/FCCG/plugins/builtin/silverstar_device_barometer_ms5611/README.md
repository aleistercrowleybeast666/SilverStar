# MS5611 barometer

One physical MS5611 plugin supplies I²C and SPI interface variants. Both use the same bounded, command-driven core. The current operating profile is `osr4096_20_hz`: a reset, eight PROM reads with CRC4, then one temperature and one pressure conversion per cycle. Each `Process` call makes at most one bus transaction. The first verified pressure/temperature sample gates readiness.

The reference pressure and temperature vector comes from the [TE Connectivity MS5611-01BA03 datasheet](https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocFormat=pdf&DocLang=English&DocNm=MS5611-01BA03&DocType=Data+Sheet&PartCntxt=MS561101BA03-50). The chip does not report altitude; the SilverStar barometer publication layer derives it from pressure. The SPI resource is limited to the datasheet's 20 MHz maximum. No physical board or flight test has been performed with this new driver (`HARDWARE_UNVERIFIED`).
