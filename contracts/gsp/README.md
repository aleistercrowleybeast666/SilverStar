# GSP-MIN wire contract

`wire.json` and `golden.json` are the shared authority for the Ground MCU and
GSHC byte streams. The two implementations keep their own parser and builder,
and integration tests compare both against the same vectors. UART and USB CDC
carry identical bytes. AIR frames inside `AIR_TX` and `AIR_RX` are opaque.

The wire format matches GS_SS1 main at
`7fe0f61142c7360f7dbae0ac0000036315631320`; the 64-byte payload ceiling
is the bounded Ground implementation limit. GSP ACK only confirms the Ground
bridge accepted a GSP request and is separate from an AIR ACK.
