# Ebyte E28-2G4M12/20/27 S/SX (shared SX128x LoRa backend)

Declarative SilverStar_FCCG builtin `device` plugin.

Reference baseline: `main` at `cc0b377ded690556d037a412a55f87fe334c42d0`. Reference-derived files retain the recorded snapshot provenance; FCCG-owned files are replayed from their declared workspace source-of-truth and identified separately in `metadata.source_origins`. Plugin payload is data and is never executed.

The existing M12SX identity and default remain intact. New variants are hardware
unverified and not flight qualified. M20 nominal 20 dBm uses chip drive -2 dBm;
M27 nominal 27 dBm uses chip drive 0 dBm. Their active-high RX_EN/TX_EN controls
require verified low startup and distinct GPIOs. All variants cap SPI at 10 MHz.
Only documented nominal powers are supported; no PA calibration ladder is inferred.
See [the variant contract and evidence](../../../../../docs/FCCG/EBYTE_RADIO_VARIANTS.md).
