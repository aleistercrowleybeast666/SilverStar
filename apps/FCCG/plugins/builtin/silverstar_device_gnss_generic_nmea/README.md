# Generic NMEA GNSS

This plugin receives NMEA 0183 GGA, GNS, RMC, VTG and GST sentences over a
user-bound UART. It does not send receiver commands. GSA DOP is ignored
because it is not metric position accuracy.

The parser checks each checksum, limits a sentence to 96 bytes and each
processing call to 256 input bytes and 8 sentences, and resynchronizes at the
next `$`. Samples are published once per UTC epoch when the next epoch arrives;
each published field comes only from that epoch. Receipt time is explicitly
untrusted as a measurement time. Vertical velocity is unavailable because the
supported sentences do not provide it. GST accuracy is exposed only when that
sentence reports usable values. Baud and output rate must be configured on the
receiver and in the hardware UART configuration by the user.

This is a software implementation. Hardware integration is unverified.
