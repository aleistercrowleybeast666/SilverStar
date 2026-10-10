# AIR Link and radio compatibility

AIR M0 is the Flight ↔ GSHC logical wire protocol. It is independent of the radio. A radio transports unchanged AIR frame bytes. The project-owned AIR Link records the AIR profile, radio technology and family, selected frequency, PHY profile, and packet MTU once. Flight and Ground firmware render the same air_link_config.h constants. Module electrical bindings and module-specific limits belong to each endpoint.

Readiness checks both endpoint radios against the selected technology/family, frequency-range overlap, PHY modes, bandwidth, spreading factor, coding rate, and minimum AIR transport MTU. A matching plugin ID is not required. Errors include AIR_LINK_NO_RADIO, AIR_LINK_FAMILY_MISMATCH, AIR_LINK_FREQUENCY_OUT_OF_RANGE, AIR_LINK_PHY_INCOMPATIBLE, and AIR_LINK_MTU_TOO_SMALL. Generation is blocked on these errors. The present verified E28-2G4M12SX profile is SX128x LoRa at 2473 MHz, SF10, 800 kHz, CR 4/5 with 16-symbol preamble, explicit header, CRC and normal IQ. The source graph deliberately rejects unverified SX128x parameter combinations.

The radio manifest separates SX128x driver/family metadata from its M12 module variant. Future module variants can provide verified limits without duplicating the driver. The schema can represent another packet-radio family, subject to AIR's packet size and bidirectional transport constraints; this round adds no other radio driver.

## Module capability evidence

The M12 manifest now separates Ebyte datasheet capability from the narrower
SilverStar validated profile. The [Ebyte M12 manual](https://www.ebyte.com/Uploadfiles/Files/2023-7-12/20237121022567349.pdf)
lists 2400–2500 MHz and a 12–14 dBm maximum output range. SilverStar's
currently validated firmware configuration remains 2473 MHz and 12 dBm.
The Telemetry Configuration editor obtains its frequency and each endpoint's
TX power limits from the selected module's validated values. Enter rejects
out-of-range drafts with an explicit validation code; it does not commit a
clamped value. Flight and Ground power remain independent. The current
firmware profile and hardware evidence do not yet justify exposing the full
datasheet range or adding M20/M27 power settings.
