"""Shared UART choices; the driver/device decides which rates actually work."""

SERIAL_BAUD_CANDIDATES = (
    "1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200",
    "230400", "460800", "921600", "1000000", "1500000", "2000000", "3000000",
)
# QIntValidator and the native serial configuration use a bounded integer.
# This is an input representation bound, not a claim of hardware support.
SERIAL_BAUD_MAX = 2_147_483_647


def SerialBaud_Parse(value: str) -> int:
    text = value.strip()
    if not text.isascii() or not text.isdecimal() or len(text) > 10:
        return 0
    baud = int(text)
    return baud if 1 <= baud <= SERIAL_BAUD_MAX else 0
