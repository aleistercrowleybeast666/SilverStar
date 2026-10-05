# SS0.5

Declarative SilverStar_FCCG builtin `board` plugin.

Reference baseline: `main` at `cc0b377ded690556d037a412a55f87fe334c42d0`. The payload retains its recorded read-only reference provenance. Plugin payload is data and is never executed.

`connections.json` is the sole fixed logical-resource authority for this verified Board. The
bundled CubeMX `.ioc` and generated headers resolve and validate physical aliases; their discovery
order never chooses a Platform table index.

| Logical ID | Fixed physical alias | Purpose |
| --- | --- | --- |
| `PLATFORM_GPIO_0` | `RADIO_NSS` | SX1281 NSS |
| `PLATFORM_GPIO_1` | `RADIO_RST` | SX1281 reset |
| `PLATFORM_GPIO_2` | `RADIO_BUSY` | SX1281 busy |
| `PLATFORM_GPIO_3` | `RADIO_DIO1` | SX1281 DIO1 |
| `PLATFORM_GPIO_4` | `P_CONTROL1` | Launch ignition power output |
| `PLATFORM_GPIO_5` | `P_CONTROL2` | Parachute pyro power output |
| `PLATFORM_GPIO_6` | `IMU_CAL_LED` | System Status Indicator |
| `PLATFORM_GPIO_7` | `GNSS_RST` | GNSS reset |
| `PLATFORM_GPIO_8` | `GNSS_TIMEPULSE` | GNSS timepulse |

UART 1–3, SPI 1, ADC 1, SDIO 1, and Time 1 follow the same declared fixed-binding rule. FCCG's
Platform Resource Closure Check rejects a missing/drifted alias or generated symbol before project
generation. The resource-binding fingerprint also makes an already generated project stale when
the connection map, snapshot, manifest, or renderer contract changes. This software verification
does not replace electrical, actuator, RF, SD-media, HIL, or flight validation.
